#!/usr/bin/env python3
"""Build ``dataset/{images,labels}/{train,val}`` + ``data.yaml`` with a split by clip tag.

Frames from one clip are near-duplicates of each other (3 fps, same floor, same lighting, same
person), so a random frame-level split leaks and reports a mAP that means nothing (HANDOFF Q2/Q3).
This script splits by *tag*: val is whole clips. Give them explicitly with ``--val-tags stair_e,new_f``
or let ``--val-frac`` pick tags (greedy, largest tags into train first, until val holds about that
share of frames). Tags with zero rat boxes are never chosen automatically for val.

Augmented frames (``--extra frames_aug:labels_aug``) go to train only, and any augmented frame whose
rat source *or* background source is a val tag is dropped, using ``labels_aug/_sources.csv``.

``GRAY=True`` converts every image to grayscale replicated to 3 channels, so the phone footage and
the NoIR/IR footage share one domain (README decision 7). It must match ``GRAY`` in
``pi/detect.py``; the value is also written into ``data.yaml`` as a comment so a mismatch is visible.

Empty-label frames are kept as negatives (``--drop-empty`` removes them; ``--max-empty-ratio``
caps them relative to positives). Prints per split and per tag counts and the share of frames with
a box, which is the number to quote when someone asks how big the training set is.

Example::

    python3 make_dataset.py --val-tags stair_e,new_f --extra frames_aug:labels_aug
"""
from __future__ import annotations

import argparse
import random
import shutil
import sys
from pathlib import Path

from common import CLASS_NAMES, label_path, list_frames, parse_tag_list, read_csv_rows, read_labels, source_tag, tag_of

GRAY = True  # must match pi/detect.py


def to_gray3(src: Path, dst: Path, cv2) -> None:
    img = cv2.imread(str(src))
    if img is None:
        shutil.copy2(src, dst)
        return
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cv2.imwrite(str(dst), cv2.cvtColor(g, cv2.COLOR_GRAY2BGR), [cv2.IMWRITE_JPEG_QUALITY, 92])


def pick_val_tags(per_tag: dict[str, list], frac: float, rng: random.Random) -> list[str]:
    total = sum(len(v) for v in per_tag.values())
    cands = [t for t, items in per_tag.items() if any(int(b[0]) == 0 for _, boxes in items for b in boxes)]
    rng.shuffle(cands)
    val, n = [], 0
    for t in cands:
        if n >= frac * total:
            break
        val.append(t)
        n += len(per_tag[t])
    return sorted(val)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", default="frames")
    ap.add_argument("--labels", default="labels")
    ap.add_argument("--extra", action="append", default=[], metavar="FRAMES:LABELS",
                    help="extra (augmented) frames+labels, train only; repeatable")
    ap.add_argument("--out", default="dataset")
    ap.add_argument("--val-tags", help="comma-separated tags that form val (whole clips)")
    ap.add_argument("--val-frac", type=float, default=0.2, help="target val share when --val-tags is not given")
    ap.add_argument("--gray", dest="gray", action="store_true", default=GRAY)
    ap.add_argument("--color", dest="gray", action="store_false", help="keep colour (must match detect.py)")
    ap.add_argument("--drop-empty", action="store_true", help="drop frames with no boxes")
    ap.add_argument("--max-empty-ratio", type=float, default=1.0, help="max empty frames per positive frame in train")
    ap.add_argument("--unreviewed-ok", action="store_true", default=True, help="(default) include frames not in _reviewed.txt")
    ap.add_argument("--reviewed-only", action="store_true", help="only frames listed in labels/_reviewed.txt")
    ap.add_argument("--link", action="store_true", help="hard-link instead of copy (only without --gray)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    try:
        import cv2
    except ImportError:
        cv2 = None
        if args.gray:
            print("opencv-python is needed for --gray", file=sys.stderr)
            return 2

    rng = random.Random(args.seed)
    frames_dir, labels_dir, out = Path(args.frames), Path(args.labels), Path(args.out)
    reviewed = set()
    rp = labels_dir / "_reviewed.txt"
    if rp.is_file():
        reviewed = {line.split("\t")[0] for line in rp.read_text().splitlines() if line.strip()}

    per_tag: dict[str, list] = {}
    for f in list_frames(frames_dir):
        if args.reviewed_only and f.stem not in reviewed:
            continue
        boxes = read_labels(label_path(labels_dir, f))
        if args.drop_empty and not boxes:
            continue
        per_tag.setdefault(tag_of(f.stem), []).append((f, boxes))
    if not per_tag:
        print(f"no frames found in {frames_dir}", file=sys.stderr)
        return 2

    val_tags = parse_tag_list(args.val_tags) or pick_val_tags(per_tag, args.val_frac, rng)
    missing = [t for t in val_tags if t not in per_tag]
    if missing:
        print(f"val tags not present in frames: {missing}  (have: {sorted(per_tag)})", file=sys.stderr)
        return 2
    val_set = set(val_tags)

    split: dict[str, list] = {"train": [], "val": []}
    for tag, items in per_tag.items():
        split["val" if tag in val_set else "train"].extend(items)

    # cap negatives in train
    if args.max_empty_ratio >= 0:
        pos = [it for it in split["train"] if it[1]]
        neg = [it for it in split["train"] if not it[1]]
        cap = int(len(pos) * args.max_empty_ratio)
        if len(neg) > cap:
            rng.shuffle(neg)
            neg = neg[:cap]
        split["train"] = pos + neg

    # augmented extras: train only, no val contamination
    n_extra, n_extra_dropped = 0, 0
    for spec in args.extra:
        try:
            ef, el = spec.split(":")
        except ValueError:
            print(f"bad --extra '{spec}', expected FRAMES:LABELS", file=sys.stderr)
            return 2
        ef, el = Path(ef), Path(el)
        sources = {r["frame"]: r for r in read_csv_rows(el / "_sources.csv")}
        for f in list_frames(ef):
            s = sources.get(f.name, {})
            touches = {source_tag(tag_of(f.stem)), s.get("rat_source", ""), s.get("bg_source", "")}
            if touches & val_set:
                n_extra_dropped += 1
                continue
            split["train"].append((f, read_labels(label_path(el, f))))
            n_extra += 1

    # write
    if out.is_dir():
        shutil.rmtree(out)
    for s in split:
        (out / "images" / s).mkdir(parents=True)
        (out / "labels" / s).mkdir(parents=True)
    for s, items in split.items():
        for f, boxes in items:
            dst_img = out / "images" / s / f.name
            if args.gray:
                to_gray3(f, dst_img, cv2)
            elif args.link:
                try:
                    dst_img.hardlink_to(f)
                except OSError:
                    shutil.copy2(f, dst_img)
            else:
                shutil.copy2(f, dst_img)
            lp = out / "labels" / s / (f.stem + ".txt")
            lp.write_text("".join(f"{int(b[0])} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f} {b[4]:.6f}\n" for b in boxes))

    names = "".join(f"  {i}: {n}\n" for i, n in enumerate(CLASS_NAMES))
    (out / "data.yaml").write_text(
        f"# built by make_dataset.py  gray={args.gray}  val_tags={','.join(val_tags)}\n"
        f"path: {out.resolve()}\ntrain: images/train\nval: images/val\nnc: {len(CLASS_NAMES)}\nnames:\n{names}")

    # report
    def summarise(items):
        n = len(items)
        nb = sum(1 for _, b in items if b)
        nr = sum(1 for _, b in items for x in b if int(x[0]) == 0)
        npn = sum(1 for _, b in items for x in b if int(x[0]) == 1)
        return n, nb, nr, npn

    print(f"dataset -> {out}/   gray={args.gray}   val tags: {', '.join(val_tags)}")
    print(f"{'split':<7}{'frames':>8}{'w/box':>8}{'share':>7}{'rat':>7}{'person':>8}")
    for s, items in split.items():
        n, nb, nr, npn = summarise(items)
        print(f"{s:<7}{n:>8}{nb:>8}{100 * nb / max(1, n):>6.0f}%{nr:>7}{npn:>8}")
    print()
    print(f"{'tag':<14}{'split':<7}{'frames':>8}{'w/box':>8}{'rat':>7}")
    for tag in sorted(per_tag):
        n, nb, nr, _ = summarise(per_tag[tag])
        print(f"{tag:<14}{'val' if tag in val_set else 'train':<7}{n:>8}{nb:>8}{nr:>7}")
    if args.extra:
        print(f"augmented: {n_extra} added to train, {n_extra_dropped} dropped because they touch a val tag")
    print("next: ./train.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
