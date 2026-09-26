#!/usr/bin/env python3
"""Save frames from the node camera to a directory: the rig recordings for training and eval.

Runs ``camera.py`` with the node's exact settings (640x480 @15, gain 8, 30 ms, greyworld) so the
saved JPEGs are in the same domain the detector will see on stage. ``--every 5`` keeps every 5th
frame (3 fps, same rate as ``extract_frames.py``); ``--seconds 60`` stops after a minute. Files are
``<tag>_<n>.jpg`` so they drop straight into ``frames/`` on the Mac and ``make_dataset.py`` treats
each recording as its own clip tag.

Saves the Y plane as an 8-bit grayscale JPEG by default (``--color`` for the I420->BGR conversion,
which shows the NoIR magenta cast).

Example (on the Pi)::

    python3 grab_frames.py --out rig/hall_a --tag hall_a --seconds 60 --every 5
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from camera import add_camera_args, frames_from_args


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_camera_args(ap)
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--tag", default=None, help="clip tag for the file names (default: directory name)")
    ap.add_argument("--seconds", type=float, default=30.0, help="record for this long (0 = until ^C)")
    ap.add_argument("--every", type=int, default=5, help="keep every Nth frame")
    ap.add_argument("--n", type=int, default=0, help="stop after N saved frames (0 = no limit)")
    ap.add_argument("--color", action="store_true", help="save BGR instead of the Y plane")
    ap.add_argument("--quality", type=int, default=92)
    args = ap.parse_args(argv)

    try:
        import cv2
    except ImportError:
        print("needs opencv-python-headless", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = args.tag or out.name
    existing = [p for p in out.glob(f"{tag}_*.jpg")]
    idx = max([int(p.stem.rsplit("_", 1)[1]) for p in existing if p.stem.rsplit("_", 1)[1].isdigit()] + [-1]) + 1
    t0 = time.monotonic()
    saved = seen = 0
    try:
        for fr in frames_from_args(args, pace=args.mock is not None):
            seen += 1
            if (seen - 1) % max(1, args.every):
                continue
            img = fr.bgr if args.color else fr.gray
            cv2.imwrite(str(out / f"{tag}_{idx:05d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
            idx += 1
            saved += 1
            if saved % 20 == 0:
                print(f"  {saved} saved ({time.monotonic() - t0:.0f}s, mean Y {float(fr.gray.mean()):.0f})", flush=True)
            if args.n and saved >= args.n:
                break
            if args.seconds and time.monotonic() - t0 >= args.seconds:
                break
    except KeyboardInterrupt:
        pass
    print(f"saved {saved} of {seen} frames to {out}/ as {tag}_*.jpg")
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
