#!/usr/bin/env python3
"""Read the Owl agent's optional JPEG handoff and save local crop events.

This process never starts a camera, imports GPIO, blinks an LED, or posts to an
API. The agent remains the only camera owner. Run this with the isolated
NumPy/OpenCV/ONNX Runtime venv and an explicit model hash and confidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import socket
import threading
import time
from pathlib import Path

from detect import (DEMO_H3, EVENT_COOLDOWN_S, FLOOR_Y, HIT_WINDOW_S,
                    HITS_NEEDED, MAX_RAT_WIDTH, MIN_RAT_WIDTH, NODE_ID,
                    PERSON_CONTAIN, PERSON_IOU, Detector, EventGate,
                    apply_rules, make_event, save_event)
from live_bridge import HEADER, MAX_JPEG_BYTES

MAX_BACKLOG_DRAIN = 32
MAX_FRAME_AGE_S = 1.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FrameProcessor:
    def __init__(self, detector, events_dir: Path, *, floor_y: float = FLOOR_Y,
                 person_iou: float = PERSON_IOU, person_contain: float = PERSON_CONTAIN,
                 min_rat_width: float = MIN_RAT_WIDTH, max_rat_width: float = MAX_RAT_WIDTH,
                 hits: int = HITS_NEEDED, window: float = HIT_WINDOW_S,
                 cooldown: float = EVENT_COOLDOWN_S, node_id: str = NODE_ID,
                 h3: str = DEMO_H3, max_frame_age_s: float = MAX_FRAME_AGE_S):
        self.detector = detector
        self.events_dir = events_dir
        self.floor_y = floor_y
        self.person_iou = person_iou
        self.person_contain = person_contain
        self.min_rat_width = min_rat_width
        self.max_rat_width = max_rat_width
        self.node_id = node_id
        self.h3 = h3
        self.max_frame_age_s = max_frame_age_s
        self.gate = EventGate(hits, window, cooldown)
        self.last_sequence: int | None = None
        self.stats = {"packets_received": 0, "backlog_dropped": 0,
                      "frames_received": 0, "frames_inferred": 0,
                      "invalid_frames": 0,
                      "invalid_timestamps": 0, "stale_frames": 0,
                      "sequence_gaps": 0, "rat_proposals": 0,
                      "rat_suppressed": 0, "events": 0,
                      "inference_ms_total": 0.0, "inference_ms_max": 0.0,
                      "frame_age_ms_total": 0.0, "frame_age_ms_max": 0.0}

    def process(self, packet: bytes, *, now_monotonic: float | None = None) -> dict | None:
        now = time.monotonic() if now_monotonic is None else now_monotonic
        if len(packet) <= HEADER.size or len(packet) > HEADER.size + MAX_JPEG_BYTES:
            self.stats["invalid_frames"] += 1
            self.gate.update(now, None)
            return None
        mono_ts, wall_ts, sequence = HEADER.unpack_from(packet)
        if not math.isfinite(mono_ts) or not math.isfinite(wall_ts):
            self.stats["invalid_timestamps"] += 1
            self.gate.update(now, None)
            return None
        if self.last_sequence is not None and sequence != self.last_sequence + 1:
            self.stats["sequence_gaps"] += 1
            self.gate.update(mono_ts, None)  # dropped frames cannot count as consecutive hits
        self.last_sequence = sequence
        age = now - mono_ts
        if age > self.max_frame_age_s or age < -self.max_frame_age_s:
            self.stats["stale_frames"] += 1
            self.gate.update(now, None)
            return None
        age_ms = max(0.0, age * 1000)
        import cv2
        import numpy as np

        try:
            frame = cv2.imdecode(np.frombuffer(packet, dtype=np.uint8, count=len(packet) - HEADER.size,
                                             offset=HEADER.size), cv2.IMREAD_COLOR)
        except cv2.error:
            frame = None
        if frame is None:
            self.stats["invalid_frames"] += 1
            self.gate.update(mono_ts, None)
            return None
        self.stats["frames_received"] += 1
        self.stats["frame_age_ms_total"] += age_ms
        self.stats["frame_age_ms_max"] = max(self.stats["frame_age_ms_max"], age_ms)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        try:
            start = time.perf_counter()
            detections = self.detector.infer(gray)
            self.stats["frames_inferred"] += 1
            infer_ms = (time.perf_counter() - start) * 1000
            self.stats["inference_ms_total"] += infer_ms
            self.stats["inference_ms_max"] = max(self.stats["inference_ms_max"], infer_ms)
        except Exception:
            self.stats["invalid_frames"] += 1
            self.gate.update(mono_ts, None)
            return None
        rats, _ = apply_rules(detections, self.floor_y, self.person_iou,
                              self.person_contain, self.min_rat_width, self.max_rat_width)
        proposals = sum(d.cls == "rat" for d in detections)
        self.stats["rat_proposals"] += proposals
        self.stats["rat_suppressed"] += proposals - len(rats)
        fired = self.gate.update(mono_ts, rats[0] if rats else None)
        if not fired:
            return None
        selected, n_hits = fired
        event = make_event(selected, n_hits, frame, self.node_id, self.h3, wall_ts)
        self.stats["events"] += 1
        save_event(self.events_dir, event, self.stats["events"])
        return event


def serve(socket_path: Path, processor: FrameProcessor, stop: threading.Event,
          ready: threading.Event | None = None, max_frames: int = 0) -> dict:
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 512 * 1024)
        old_umask = os.umask(0o077)
        try:
            listener.bind(str(socket_path))
        finally:
            os.umask(old_umask)
        owned_inode = socket_path.stat().st_ino
        listener.settimeout(0.1)
        if ready:
            ready.set()
        packets = 0
        started = time.monotonic()
        try:
            while not stop.is_set():
                try:
                    packet = listener.recv(HEADER.size + MAX_JPEG_BYTES + 1)
                except socket.timeout:
                    continue
                packets += 1
                # If inference fell behind, discard queued JPEGs and use the
                # newest frame. The sequence gap resets the three-hit gate.
                listener.setblocking(False)
                try:
                    for _ in range(MAX_BACKLOG_DRAIN):
                        try:
                            newer = listener.recv(HEADER.size + MAX_JPEG_BYTES + 1)
                        except BlockingIOError:
                            break
                        packet = newer
                        packets += 1
                        processor.stats["backlog_dropped"] += 1
                finally:
                    listener.settimeout(0.1)
                processor.stats["packets_received"] = packets
                event = processor.process(packet)
                if event:
                    print(f"event {processor.stats['events']} {event['ts']} "
                          f"conf={event['conf']} bbox={event['bbox']} crop-only", flush=True)
                if max_frames and packets >= max_frames:
                    break
        finally:
            if socket_path.exists() and socket_path.stat().st_ino == owned_inode:
                socket_path.unlink()
        stats = dict(processor.stats)
        elapsed = max(time.monotonic() - started, 1e-9)
        stats.update({"elapsed_s": round(elapsed, 3),
                      "received_fps": round(packets / elapsed, 2),
                      "processed_fps": round(stats["frames_inferred"] / elapsed, 2),
                      "inference_ms_mean": round(stats["inference_ms_total"] / max(stats["frames_inferred"], 1), 2),
                      "frame_age_ms_mean": round(stats["frame_age_ms_total"] / max(stats["frames_received"], 1), 2)})
        return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--socket", type=Path, required=True)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--expected-sha256", required=True, help="locked ONNX SHA256")
    ap.add_argument("--events-dir", type=Path, required=True, help="new directory for crop-only events")
    ap.add_argument("--conf", type=float, required=True, help="explicit selected runtime confidence")
    ap.add_argument("--iou", type=float, default=0.45)
    ap.add_argument("--floor-y", type=float, default=FLOOR_Y)
    ap.add_argument("--hits", type=int, default=HITS_NEEDED)
    ap.add_argument("--window", type=float, default=HIT_WINDOW_S)
    ap.add_argument("--cooldown", type=float, default=EVENT_COOLDOWN_S)
    ap.add_argument("--person-iou", type=float, default=PERSON_IOU)
    ap.add_argument("--person-contain", type=float, default=PERSON_CONTAIN)
    ap.add_argument("--min-rat-width", type=float, default=MIN_RAT_WIDTH)
    ap.add_argument("--max-rat-width", type=float, default=MAX_RAT_WIDTH)
    ap.add_argument("--node-id", default=NODE_ID)
    ap.add_argument("--h3", default=DEMO_H3)
    ap.add_argument("--max-frames", type=int, default=0, help="stop after N received frames (test only)")
    ap.add_argument("--max-frame-age", type=float, default=MAX_FRAME_AGE_S,
                    help="discard frames older than this many seconds")
    args = ap.parse_args(argv)
    if not args.model.is_file() or sha256(args.model) != args.expected_sha256:
        ap.error("model is missing or SHA256 does not match --expected-sha256")
    if (not 0 <= args.conf <= 1 or not 0 <= args.iou <= 1 or args.hits < 1 or
            args.window <= 0 or args.max_frame_age <= 0):
        ap.error("invalid detector or gate settings")
    args.events_dir.mkdir(parents=True, exist_ok=False)
    config = {"model": str(args.model.resolve()), "model_sha256": args.expected_sha256,
              "socket": str(args.socket.resolve()), "grayscale": True, "conf": args.conf,
              "iou": args.iou, "floor_y": args.floor_y, "hits": args.hits,
              "window": args.window, "cooldown": args.cooldown,
              "person_iou": args.person_iou, "person_contain": args.person_contain,
              "min_rat_width": args.min_rat_width, "max_rat_width": args.max_rat_width,
              "node_id": args.node_id, "h3": args.h3, "api_post": False, "gpio_led": False,
              "max_frame_age_s": args.max_frame_age, "max_backlog_drain": MAX_BACKLOG_DRAIN,
              "started_at_unix": time.time()}
    (args.events_dir / "run_config.json").write_text(json.dumps(config, indent=2) + "\n")
    detector = Detector(str(args.model), gray=True, conf=args.conf, iou=args.iou)
    processor = FrameProcessor(detector, args.events_dir, floor_y=args.floor_y,
                               person_iou=args.person_iou, person_contain=args.person_contain,
                               min_rat_width=args.min_rat_width, max_rat_width=args.max_rat_width,
                               hits=args.hits, window=args.window, cooldown=args.cooldown,
                               node_id=args.node_id, h3=args.h3,
                               max_frame_age_s=args.max_frame_age)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    stats = serve(args.socket, processor, stop, max_frames=args.max_frames)
    (args.events_dir / "run_stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
