"""Optional, nonblocking JPEG handoff from the existing Owl camera agent.

The agent's camera callback calls ``FrameHandoff(jpeg)``. A one-slot queue and a
separate sender thread keep socket failures and slow inference out of that
callback. This module uses only Python's standard library, so the agent's
system Python does not need the detector's packages.
"""
from __future__ import annotations

import os
import queue
import socket
import struct
import threading
import time


HEADER = struct.Struct("!ddQ")  # source monotonic time, wall time, frame sequence
MAX_JPEG_BYTES = 200_000


class FrameHandoff:
    def __init__(self, socket_path: str, max_jpeg_bytes: int = MAX_JPEG_BYTES):
        if not socket_path:
            raise ValueError("socket_path is required")
        self.socket_path = socket_path
        self.max_jpeg_bytes = max_jpeg_bytes
        self.pending: queue.Queue[tuple[int, float, float, bytes]] = queue.Queue(maxsize=1)
        self.stopping = threading.Event()
        self.frames_seen = 0
        self.overwritten = 0
        self.oversized = 0
        self.sent = 0
        self.send_failed = 0
        self.thread = threading.Thread(target=self._send_loop, name="owl-detector-handoff", daemon=True)
        self.thread.start()

    def __call__(self, jpeg: bytes) -> None:
        """Never wait for the detector or let a bridge failure reach the camera."""
        try:
            if self.stopping.is_set():
                return
            self.frames_seen += 1
            if len(jpeg) > self.max_jpeg_bytes:
                self.oversized += 1
                return
            item = (self.frames_seen, time.monotonic(), time.time(), jpeg)
            try:
                self.pending.put_nowait(item)
            except queue.Full:
                try:
                    self.pending.get_nowait()
                    self.overwritten += 1
                except queue.Empty:
                    pass  # the sender took it between put and get
                self.pending.put_nowait(item)
        except Exception:
            # Camera._read calls callbacks inline. Even a local bridge bug must
            # leave recording and streaming callbacks alive.
            self.send_failed += 1

    def _send_loop(self) -> None:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
                sock.setblocking(False)
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 512 * 1024)
                except OSError:
                    pass
                while not self.stopping.is_set():
                    try:
                        sequence, mono_ts, wall_ts, jpeg = self.pending.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    try:
                        sock.sendto(HEADER.pack(mono_ts, wall_ts, sequence) + jpeg, self.socket_path)
                        self.sent += 1
                    except OSError:
                        # No worker, a full socket, or a worker that restarted.
                        # The next frame tries the path again without reconnect state.
                        self.send_failed += 1
        except Exception:
            self.send_failed += 1

    def close(self) -> None:
        self.stopping.set()
        self.thread.join(timeout=1)


def from_env(environ: dict[str, str] | None = None) -> FrameHandoff | None:
    path = (environ if environ is not None else os.environ).get("OWL_DETECT_SOCKET", "").strip()
    return FrameHandoff(path) if path else None
