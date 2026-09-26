#!/usr/bin/env python3
"""Frame source for the node: ``rpicam-vid`` raw YUV420 on stdout, or a directory of JPEGs (``--mock``).

The Pi has no ``picamera2`` and no internet, so the camera is driven through the stock
``rpicam-vid`` binary and its stdout is parsed here. Command used (README §4)::

    rpicam-vid -t 0 --codec yuv420 --width 640 --height 480 --framerate 15 \\
               --gain 8 --shutter 30000 --awb greyworld --nopreview -o -

Each frame is ``width*height*3/2`` bytes of planar I420: the Y plane first (that is the grayscale
image the detector runs on, no conversion needed), then U and V at quarter size. ``Frame.gray``
is the Y plane; ``Frame.bgr`` converts the whole thing only when asked for (the event crop). Both
are numpy arrays; only numpy and opencv-python-headless are imported.

Gain 8 / 30 ms shutter / greyworld AWB are the settings that gave usable IR-lit frames on 09-23;
change them on the command line, not here. At 640x480 the stride equals the width; other sizes may
be padded to a multiple of 64 by libcamera, in which case pass ``--stride``.

Library use::

    from camera import frames
    for fr in frames(mock="frames_mock"):   # or frames() on the Pi
        do(fr.gray)

CLI: ``python3 camera.py --n 30`` prints the fps it gets; ``--mock DIR --show`` on a Mac.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

DEFAULTS = dict(width=640, height=480, fps=15, gain=8, shutter=30000, awb="greyworld")
IMG_EXTS = {".jpg", ".jpeg", ".png"}


def rpicam_cmd(width=640, height=480, fps=15, gain=8, shutter=30000, awb="greyworld", extra=()):
    return ["rpicam-vid", "-t", "0", "--codec", "yuv420", "--width", str(width), "--height", str(height),
            "--framerate", str(fps), "--gain", str(gain), "--shutter", str(shutter), "--awb", awb,
            "--nopreview", *extra, "-o", "-"]


class Frame:
    """One frame. ``gray`` is always available; ``bgr`` is computed on first access."""

    __slots__ = ("ts", "index", "_yuv", "_gray", "_bgr", "w", "h", "source")

    def __init__(self, ts: float, index: int, w: int, h: int, yuv=None, gray=None, bgr=None, source: str = ""):
        self.ts, self.index, self.w, self.h = ts, index, w, h
        self._yuv, self._gray, self._bgr, self.source = yuv, gray, bgr, source

    @property
    def gray(self):
        if self._gray is None:
            if self._yuv is not None:
                self._gray = self._yuv[: self.h, : self.w]
            else:
                import cv2
                self._gray = cv2.cvtColor(self._bgr, cv2.COLOR_BGR2GRAY)
        return self._gray

    @property
    def bgr(self):
        if self._bgr is None:
            import cv2
            if self._yuv is not None:
                self._bgr = cv2.cvtColor(self._yuv, cv2.COLOR_YUV2BGR_I420)
            else:
                self._bgr = cv2.cvtColor(self._gray, cv2.COLOR_GRAY2BGR)
        return self._bgr

    @property
    def has_color(self) -> bool:
        return self._yuv is not None or self._bgr is not None


def _mock_frames(mock_dir: str, fps: float, loop: bool, pace: bool):
    import cv2

    files = sorted(p for p in Path(mock_dir).iterdir() if p.suffix.lower() in IMG_EXTS and not p.name.startswith("_"))
    if not files:
        raise SystemExit(f"no images in {mock_dir}")
    i = 0
    t0 = time.monotonic()
    while True:
        for p in files:
            img = cv2.imread(str(p))
            if img is None:
                continue
            if pace and fps > 0:
                target = t0 + i / fps
                d = target - time.monotonic()
                if d > 0:
                    time.sleep(d)
            h, w = img.shape[:2]
            yield Frame(time.time(), i, w, h, bgr=img, source=p.name)
            i += 1
        if not loop:
            return


def frames(mock: str | None = None, width=640, height=480, fps=15, gain=8, shutter=30000, awb="greyworld",
           stride: int | None = None, loop=False, pace=True, extra=()):
    """Generator of ``Frame``. On the Pi it spawns rpicam-vid; with ``mock`` it walks a directory."""
    if mock:
        yield from _mock_frames(mock, fps, loop, pace)
        return

    import numpy as np

    stride = stride or width
    nbytes = stride * height * 3 // 2
    cmd = rpicam_cmd(width, height, fps, gain, shutter, awb, extra)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=nbytes * 4)
    i = 0
    try:
        while True:
            buf = bytearray()
            while len(buf) < nbytes:
                chunk = proc.stdout.read(nbytes - len(buf))
                if not chunk:
                    break
                buf += chunk
            if len(buf) < nbytes:
                break  # rpicam-vid exited
            yuv = np.frombuffer(bytes(buf), dtype=np.uint8).reshape(height * 3 // 2, stride)
            if stride != width:
                # keep the planar layout valid for cv2: crop each plane's rows to `width`
                yuv = np.ascontiguousarray(yuv[:, :width])
            yield Frame(time.time(), i, width, height, yuv=yuv, source="rpicam")
            i += 1
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:  # noqa: BLE001
            proc.kill()


def add_camera_args(ap: argparse.ArgumentParser) -> None:
    g = ap.add_argument_group("camera")
    g.add_argument("--mock", metavar="DIR", help="iterate JPEGs in DIR instead of the camera")
    g.add_argument("--loop", action="store_true", help="with --mock: loop forever")
    g.add_argument("--width", type=int, default=DEFAULTS["width"])
    g.add_argument("--height", type=int, default=DEFAULTS["height"])
    g.add_argument("--fps", type=float, default=DEFAULTS["fps"])
    g.add_argument("--gain", type=float, default=DEFAULTS["gain"])
    g.add_argument("--shutter", type=int, default=DEFAULTS["shutter"], help="microseconds")
    g.add_argument("--awb", default=DEFAULTS["awb"])
    g.add_argument("--stride", type=int, default=None, help="row stride if libcamera pads the width")


def frames_from_args(args, pace=True):
    return frames(mock=args.mock, width=args.width, height=args.height, fps=args.fps, gain=args.gain,
                  shutter=args.shutter, awb=args.awb, stride=args.stride, loop=getattr(args, "loop", False), pace=pace)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_camera_args(ap)
    ap.add_argument("--n", type=int, default=30, help="frames to read before exiting (0 = forever)")
    ap.add_argument("--show", action="store_true", help="cv2.imshow (Mac / desktop only)")
    ap.add_argument("--save", metavar="PATH", help="write the last frame as JPEG")
    args = ap.parse_args(argv)

    t0 = time.monotonic()
    n = 0
    last = None
    try:
        for fr in frames_from_args(args, pace=args.mock is not None):
            n += 1
            last = fr
            if args.show:
                import cv2
                cv2.imshow("camera", fr.bgr if fr.has_color else fr.gray)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            if args.n and n >= args.n:
                break
    except KeyboardInterrupt:
        pass
    dt = time.monotonic() - t0
    print(f"{n} frames in {dt:.2f}s = {n / dt if dt else 0:.1f} fps"
          + (f"  ({last.w}x{last.h}, mean Y {float(last.gray.mean()):.1f})" if last is not None else ""))
    if args.save and last is not None:
        import cv2
        cv2.imwrite(args.save, last.bgr if last.has_color else last.gray)
        print(f"saved {args.save}")
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
