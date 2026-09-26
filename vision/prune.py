#!/usr/bin/env python3
"""Move blurry, near-duplicate and walk-in frames out of ``frames/`` into ``frames_pruned/``.

Three reasons, checked in this order, first one wins:

- ``blur``: variance of the Laplacian of the grayscale frame below ``--blur`` (60). Motion-blurred
  frames from the phone panning teach the detector nothing and put smeared boxes in the labels.
- ``walkin``: ``--walkin TAG:START-END`` (repeatable) drops the index range where the person is
  walking into or out of shot, e.g. ``--walkin corr_d:0-24 --walkin corr_d:410-460``. These are the
  frames where the prop is still in someone's hand or the string is fully visible.
- ``dup``: dHash (8x8, 64 bit) Hamming distance to the *previous kept frame of the same tag* below
  ``--dhash`` (6). At 3 fps a static scene produces runs of identical frames; keeping one of each
  run is what "3,186 kept / 866 pruned" means in the handoff table.

Labels move with their frames (``frames_pruned/labels/``) so ``frames/`` and ``labels/`` stay in
sync, and ``frames_pruned/_pruned.csv`` records frame, reason, value. ``--restore`` moves everything
back. Counts per reason and per tag are printed at the end.

Example::

    python3 prune.py --blur 60 --dhash 6 --walkin corr_d:0-24 --dry-run
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from common import append_csv_row, index_of, label_path, list_frames, tag_of

PRUNED_FIELDS = ["frame", "tag", "reason", "value"]


def parse_walkin(specs: list[str]) -> dict[str, list[tuple[int, int]]]:
    out: dict[str, list[tuple[int, int]]] = {}
    for s in specs or []:
        try:
            tag, rng = s.rsplit(":", 1)
            a, b = rng.split("-")
            out.setdefault(tag, []).append((int(a), int(b)))
        except ValueError:
            raise SystemExit(f"bad --walkin '{s}', expected TAG:START-END")
    return out


def lap_var(gray, cv2) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def dhash(gray, cv2, np) -> int:
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA).astype(np.int16)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def move(frame: Path, labels_dir: Path, out_dir: Path, dry: bool) -> None:
    if dry:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "labels").mkdir(exist_ok=True)
    shutil.move(str(frame), str(out_dir / frame.name))
    lp = label_path(labels_dir, frame)
    if lp.is_file():
        shutil.move(str(lp), str(out_dir / "labels" / lp.name))


def restore(frames_dir: Path, labels_dir: Path, out_dir: Path) -> int:
    n = 0
    for f in list_frames(out_dir):
        shutil.move(str(f), str(frames_dir / f.name))
        lp = out_dir / "labels" / (f.stem + ".txt")
        if lp.is_file():
            labels_dir.mkdir(exist_ok=True)
            shutil.move(str(lp), str(labels_dir / lp.name))
        n += 1
    p = out_dir / "_pruned.csv"
    if p.is_file():
        p.unlink()
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", default="frames")
    ap.add_argument("--labels", default="labels")
    ap.add_argument("--out", default="frames_pruned")
    ap.add_argument("--blur", type=float, default=60.0, help="Laplacian variance threshold (0 disables)")
    ap.add_argument("--dhash", type=int, default=6, help="dHash Hamming distance below which a frame is a dup (0 disables)")
    ap.add_argument("--walkin", action="append", metavar="TAG:START-END", help="index range to drop, repeatable")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", action="store_true", help="move everything in --out back and exit")
    args = ap.parse_args(argv)

    frames_dir, labels_dir, out_dir = Path(args.frames), Path(args.labels), Path(args.out)
    if args.restore:
        n = restore(frames_dir, labels_dir, out_dir)
        print(f"restored {n} frames")
        return 0

    try:
        import cv2
        import numpy as np
    except ImportError:
        print("needs opencv-python and numpy", file=sys.stderr)
        return 2

    walkin = parse_walkin(args.walkin)
    frames = list_frames(frames_dir)
    if not frames:
        print(f"no frames in {frames_dir}")
        return 0

    counts = {"blur": 0, "walkin": 0, "dup": 0}
    per_tag: dict[str, dict[str, int]] = {}
    last_hash: dict[str, int] = {}
    kept = 0
    for f in frames:
        tag, idx = tag_of(f.stem), index_of(f.stem)
        pt = per_tag.setdefault(tag, {"kept": 0, "blur": 0, "walkin": 0, "dup": 0})
        img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        if img is None:
            reason, value = "blur", 0.0  # unreadable counts as unusable
        else:
            reason, value = "", 0.0
            if args.blur > 0:
                lv = lap_var(img, cv2)
                if lv < args.blur:
                    reason, value = "blur", lv
            if not reason and any(a <= idx <= b for a, b in walkin.get(tag, [])):
                reason, value = "walkin", idx
            if not reason and args.dhash > 0:
                h = dhash(img, cv2, np)
                prev = last_hash.get(tag)
                if prev is not None and hamming(prev, h) < args.dhash:
                    reason, value = "dup", hamming(prev, h)
                else:
                    last_hash[tag] = h
        if reason:
            counts[reason] += 1
            pt[reason] += 1
            move(f, labels_dir, out_dir, args.dry_run)
            if not args.dry_run:
                append_csv_row(out_dir / "_pruned.csv", PRUNED_FIELDS,
                               {"frame": f.name, "tag": tag, "reason": reason, "value": f"{value:.2f}"})
        else:
            kept += 1
            pt["kept"] += 1

    print(("DRY RUN  " if args.dry_run else "") + f"kept {kept}  pruned {sum(counts.values())}  "
          f"(blur {counts['blur']}, walkin {counts['walkin']}, dup {counts['dup']})")
    print(f"{'tag':<14}{'kept':>6}{'blur':>6}{'walk':>6}{'dup':>6}")
    for tag in sorted(per_tag):
        c = per_tag[tag]
        print(f"{tag:<14}{c['kept']:>6}{c['blur']:>6}{c['walkin']:>6}{c['dup']:>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
