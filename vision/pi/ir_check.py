#!/usr/bin/env python3
"""Is the 850 nm illuminator on? Grab a frame (or read ``--image``) and report the luminance.

The IR board runs off its own power bank and has no status LED you can see from the rail, so
this is the check before a demo run. It reports the mean Y (luminance) of the frame, the ratio
of the centre patch to the outer ring (an IR board pointed at the floor makes a hotspot in the
middle of the image), and a verdict::

    IR ON     mean >= --thresh (40) and centre/outer ratio >= --hotspot (1.15)
    AMBIENT   bright but no hotspot: room light is on, IR unknown (turn the room light off)
    DARK      mean below threshold: no IR, or lens cap, or the board is pointed elsewhere

With the NoIR camera in colour mode a magenta cast is normal (IR leaks into R and B) and is not a
fault. Exit code 0 for IR ON, 1 otherwise, so it can gate a script.

Examples::

    python3 ir_check.py                       # on the Pi
    python3 ir_check.py --image ../captures/ir_01.jpg
"""
from __future__ import annotations

import argparse
import sys


def analyse(gray, thresh: float, hotspot: float, np):
    h, w = gray.shape[:2]
    mean = float(gray.mean())
    cy0, cy1 = int(h * 0.35), int(h * 0.65)
    cx0, cx1 = int(w * 0.35), int(w * 0.65)
    centre = float(gray[cy0:cy1, cx0:cx1].mean())
    mask = np.ones_like(gray, dtype=bool)
    mask[cy0:cy1, cx0:cx1] = False
    outer = float(gray[mask].mean()) if mask.any() else centre
    ratio = centre / max(outer, 1e-6)
    p99 = float(np.percentile(gray, 99))
    sat = float((gray >= 250).mean())
    if mean >= thresh and ratio >= hotspot:
        verdict = "IR ON"
    elif mean >= thresh:
        verdict = "AMBIENT"
    else:
        verdict = "DARK"
    return dict(mean=mean, centre=centre, outer=outer, ratio=ratio, p99=p99, saturated=sat, verdict=verdict)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", help="analyse this file instead of grabbing a frame")
    ap.add_argument("--mock", metavar="DIR", help="grab from a JPEG directory (camera.py --mock)")
    ap.add_argument("--thresh", type=float, default=40.0, help="mean Y below this is DARK")
    ap.add_argument("--hotspot", type=float, default=1.15, help="centre/outer ratio at or above this is a hotspot")
    ap.add_argument("--warmup", type=int, default=5, help="frames to discard while AGC settles")
    ap.add_argument("--save", metavar="PATH", help="save the analysed frame")
    args = ap.parse_args(argv)

    try:
        import cv2
        import numpy as np
    except ImportError as e:
        print(f"missing dependency: {e}", file=sys.stderr)
        return 2

    if args.image:
        gray = cv2.imread(args.image, cv2.IMREAD_GRAYSCALE)
        if gray is None:
            print(f"cannot read {args.image}", file=sys.stderr)
            return 2
        src = args.image
    else:
        from camera import frames

        gray, src = None, "camera"
        for i, fr in enumerate(frames(mock=args.mock, pace=False)):
            gray = fr.gray
            if i >= args.warmup:
                break
        if gray is None:
            print("no frame from the camera", file=sys.stderr)
            return 2
    r = analyse(gray, args.thresh, args.hotspot, np)
    print(f"{src}: mean Y {r['mean']:.1f}  centre {r['centre']:.1f}  outer {r['outer']:.1f}  ratio {r['ratio']:.2f}  "
          f"p99 {r['p99']:.0f}  saturated {100 * r['saturated']:.1f}%")
    print(r["verdict"] + {"IR ON": "", "AMBIENT": "  (room light on; kill it and rerun)",
                          "DARK": "  (check the IR power bank, its switch, and where the board points)"}[r["verdict"]])
    if args.save:
        cv2.imwrite(args.save, gray)
    return 0 if r["verdict"] == "IR ON" else 1


if __name__ == "__main__":
    sys.exit(main())
