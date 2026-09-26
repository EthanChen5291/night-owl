#!/usr/bin/env python3
"""Replay a recorded camera video through the Pi detector and optionally POST events.

This reads every video frame at its recorded FPS. The gate uses clip time, while POST bodies use
the current wall-clock time so a local dashboard can show the event during a demo. The JSON
report describes the clip and every event; it is exploratory, never a formal event-gate pass.
Use eval_events.py with annotated pushes and a negatives reel for the formal gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "pi"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clip_time(frame_index: int, fps: float, pos_ms: float, previous: float | None,
              origin_ms: float = 0.0) -> float:
    """Use container timestamps when monotonic, otherwise the video's FPS."""
    fallback = frame_index / fps
    pts = (pos_ms - origin_ms) / 1000.0
    if frame_index == 0:
        return 0.0
    if pts > 0 and (previous is None or pts > previous):
        return pts
    return fallback


def main(argv=None) -> int:
    from detect import (CONF, DEMO_H3, EVENT_COOLDOWN_S, FLOOR_Y, GRAY, HIT_WINDOW_S,
                        HITS_NEEDED, IOU, MAX_RAT_WIDTH, MIN_RAT_WIDTH, NODE_ID,
                        PERSON_CONTAIN, PERSON_IOU, Detector, EventGate, apply_rules,
                        make_event, post_event, save_event)

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clip", required=True, help="recorded video, not sparse extracted frames")
    ap.add_argument("--model", required=True, help="candidate or deployed ONNX model")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--post", action="store_true", help="POST each event to the local API")
    ap.add_argument("--no-pace", action="store_true", help="process faster than real time for offline inspection")
    ap.add_argument("--save-events", help="save event JSON and crop JPEG files")
    ap.add_argument("--json", help="write a machine-readable replay report")
    ap.add_argument("--pushes", help="optional CSV of actual push times; exploratory one-to-one scoring")
    ap.add_argument("--fps", type=float, help="override missing or incorrect video FPS metadata")
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--start-sec", type=float, default=0.0, help="seek to this clip time for a short demo segment")
    ap.add_argument("--duration-sec", type=float, default=0.0, help="replay this many seconds (0 = to clip end)")
    ap.add_argument("--conf", type=float, default=CONF)
    ap.add_argument("--iou", type=float, default=IOU)
    ap.add_argument("--floor-y", type=float, default=FLOOR_Y,
                    help="minimum rat-box center y (overhead tabletop default 0)")
    ap.add_argument("--min-rat-width", type=float, default=MIN_RAT_WIDTH)
    ap.add_argument("--max-rat-width", type=float, default=MAX_RAT_WIDTH)
    ap.add_argument("--person-iou", type=float, default=PERSON_IOU)
    ap.add_argument("--person-contain", type=float, default=PERSON_CONTAIN)
    ap.add_argument("--hits", type=int, default=HITS_NEEDED)
    ap.add_argument("--window", type=float, default=HIT_WINDOW_S)
    ap.add_argument("--cooldown", type=float, default=EVENT_COOLDOWN_S)
    ap.add_argument("--color", dest="gray", action="store_false", default=GRAY)
    ap.add_argument("--node-id", default=NODE_ID)
    ap.add_argument("--h3", default=DEMO_H3)
    args = ap.parse_args(argv)
    import cv2
    clip, model = Path(args.clip), Path(args.model)
    if not clip.is_file() or not model.is_file():
        ap.error("--clip and --model must be existing files")
    cap = cv2.VideoCapture(str(clip))
    if not cap.isOpened():
        ap.error(f"cannot open {clip}")
    fps = args.fps or cap.get(cv2.CAP_PROP_FPS)
    if not 0 < fps < 240:
        ap.error("video has no valid FPS; supply --fps")
    if args.start_sec < 0 or args.duration_sec < 0:
        ap.error("--start-sec and --duration-sec must be nonnegative")
    first_frame = round(args.start_sec * fps)
    if first_frame:
        cap.set(cv2.CAP_PROP_POS_FRAMES, first_frame)
    detector = Detector(str(model), gray=args.gray, conf=args.conf, iou=args.iou)
    gate = EventGate(args.hits, args.window, args.cooldown)
    save_dir = Path(args.save_events) if args.save_events else None
    events = []
    index = first_frame
    frames_read = 0
    previous_ts = None
    origin_ms = 0.0 if first_frame else None
    segment_start = None
    wall_start = time.monotonic()
    try:
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            if origin_ms is None:
                origin_ms = pos_ms
            t_sec = clip_time(index, fps, pos_ms, previous_ts, origin_ms)
            if segment_start is None:
                segment_start = t_sec
            if args.duration_sec and t_sec - segment_start >= args.duration_sec:
                break
            previous_ts = t_sec
            if not args.no_pace:
                delay = wall_start + t_sec - segment_start - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
            frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if args.gray else bgr
            dets = detector.infer(frame)
            rats, _ = apply_rules(dets, args.floor_y, args.person_iou, args.person_contain,
                                  args.min_rat_width, args.max_rat_width)
            fired = gate.update(t_sec, rats[0] if rats else None)
            if fired:
                selected, n_hits = fired
                body = make_event(selected, n_hits, bgr, args.node_id, args.h3, time.time())
                updated, response = post_event(args.api, body) if args.post else (False, "not_requested")
                if save_dir:
                    save_event(save_dir, body, len(events) + 1)
                events.append({"clip_t_sec": round(t_sec, 3), "frame_index": index,
                               "conf": selected.conf, "bbox": selected.bbox, "n_hits": n_hits,
                               "score_updated": updated, "post_result": response})
                print(f"event {len(events)} at {t_sec:.2f}s frame {index}: conf {selected.conf:.3f} "
                      f"bbox {selected.bbox} POST {response}", flush=True)
            index += 1
            frames_read += 1
            if args.max_frames and frames_read >= args.max_frames:
                break
    finally:
        cap.release()
    report = {"status": "EXPLORATORY_REPLAY", "clip": str(clip.resolve()),
              "clip_sha256": sha256(clip), "model": str(model.resolve()),
              "model_sha256": sha256(model), "recorded_fps": fps, "frames_read": frames_read,
              "start_sec": segment_start or 0.0,
              "end_sec": previous_ts or 0.0,
              "duration_sec": (previous_ts - segment_start) if previous_ts is not None else 0.0,
              "gray": args.gray, "conf": args.conf,
              "floor_y": args.floor_y, "min_rat_width": args.min_rat_width,
              "max_rat_width": args.max_rat_width, "hits": args.hits, "window": args.window,
              "cooldown": args.cooldown, "events": events}
    if args.pushes:
        from eval_events import read_pushes, score_pushes
        pushes = read_pushes(Path(args.pushes))
        hit, false = score_pushes([(e["clip_t_sec"], e["conf"]) for e in events], pushes, .5, 3.0)
        report["push_scoring"] = {"annotated_pushes": len(pushes), "hit": hit,
                                  "false_events": len(false), "recall": hit / len(pushes) if pushes else None}
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"report {out}")
    print(f"done: {frames_read} frames, {report['duration_sec']:.2f}s replay, {len(events)} events")
    return 0


if __name__ == "__main__":
    sys.exit(main())
