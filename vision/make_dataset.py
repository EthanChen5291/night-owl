#!/usr/bin/env python3
"""Build ``dataset/{images,labels}/{train,val}`` + ``data.yaml`` with a split by clip tag.

Frames from one clip are near-duplicates of each other (3 fps, same floor, same lighting, same
person), so a random frame-level split leaks and reports a mAP that means nothing (HANDOFF Q2/Q3).
This script splits by *tag*: val is whole clips. Give them explicitly with ``--val-tags stair_e,new_f``
or let ``--val-frac`` pick tags. Both splits must include rat boxes and reviewed empty negatives.

Augmented frames (``--extra frames_aug:labels_aug``) go to train only, and any augmented frame whose
rat source *or* background source is a val tag is dropped, using ``labels_aug/_sources.csv``.

``GRAY=True`` converts every image to grayscale replicated to 3 channels, so the phone footage and
the NoIR/IR footage share one domain (README decision 7). It must match ``GRAY`` in
``pi/detect.py``; the value is also written into ``data.yaml`` as a comment so a mismatch is visible.

Only frames listed in ``labels/_reviewed.txt`` are included by default; every selected frame
needs a label file, which may be empty for a reviewed negative. ``--allow-unreviewed`` is an
explicit demo override. Prints counts by split and tag and writes ``dataset/manifest.json``.
An existing output directory is left untouched unless ``--replace`` is given.

Example::

    python3 make_dataset.py --val-tags stair_e,new_f --extra frames_aug:labels_aug
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from pathlib import Path

from common import CLASS_NAMES, label_path, list_frames, parse_tag_list, read_csv_rows, source_tag, tag_of

GRAY = True  # must match pi/detect.py


def to_gray3(src: Path, dst: Path, cv2) -> None:
    img = cv2.imread(str(src))
    if img is None:
        raise ValueError(f"cannot decode image: {src}")
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if not cv2.imwrite(str(dst), cv2.cvtColor(g, cv2.COLOR_GRAY2BGR), [cv2.IMWRITE_JPEG_QUALITY, 92]):
        raise OSError(f"cannot write grayscale image: {dst}")


def pick_val_tags(per_tag: dict[str, list], frac: float, rng: random.Random) -> list[str]:
    total = sum(len(v) for v in per_tag.values())
    cands = list(per_tag)
    rng.shuffle(cands)
    # Reserve whole clips that contain a rat and reviewed empty frames.
    positive = [t for t in cands if any(int(b[0]) == 0 for _, boxes in per_tag[t] for b in boxes)]
    negative = [t for t in cands if any(not boxes for _, boxes in per_tag[t])]
    if not positive or not negative:
        return []
    val = [positive[0]]
    if not any(not boxes for _, boxes in per_tag[val[0]]):
        other = next((t for t in negative if t not in val), None)
        if other:
            val.append(other)
    n = sum(len(per_tag[t]) for t in val)
    for t in cands:
        if t in val:
            continue
        if n >= frac * total:
            break
        val.append(t)
        n += len(per_tag[t])
    return sorted(val)


def check_label(path: Path) -> list[list[float]]:
    if not path.is_file():
        raise ValueError(f"missing label: {path}; an empty file is required for a reviewed negative")
    boxes = []
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"{path}:{line_no}: expected class cx cy w h")
        try:
            cls = int(parts[0])
            values = [float(x) for x in parts[1:]]
        except ValueError as exc:
            raise ValueError(f"{path}:{line_no}: invalid number") from exc
        cx, cy, w, h = values
        if cls not in (0, 1) or not (0 < w <= 1 and 0 < h <= 1 and
                                   0 <= cx - w / 2 and cx + w / 2 <= 1 and
                                   0 <= cy - h / 2 and cy + h / 2 <= 1):
            raise ValueError(f"{path}:{line_no}: invalid class or box outside image")
        boxes.append([cls, *values])
    return boxes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", default="frames")
    ap.add_argument("--labels", default="labels")
    ap.add_argument("--extra", action="append", default=[], metavar="FRAMES:LABELS",
                    help="extra (augmented) frames+labels, train only; repeatable")
    ap.add_argument("--out", default="dataset")
    ap.add_argument("--replace", action="store_true", help="delete and rebuild an existing output directory")
    ap.add_argument("--val-tags", help="comma-separated tags that form val (whole clips)")
    ap.add_argument("--val-frac", type=float, default=0.2, help="target val share when --val-tags is not given")
    ap.add_argument("--gray", dest="gray", action="store_true", default=GRAY)
    ap.add_argument("--color", dest="gray", action="store_false", help="keep colour (must match detect.py)")
    ap.add_argument("--drop-empty", action="store_true", help="drop frames with no boxes")
    ap.add_argument("--max-empty-ratio", type=float, default=1.0, help="max empty frames per positive frame in train")
    ap.add_argument("--allow-unreviewed", action="store_true", help="exploratory build only; training gate rejects it")
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
        if f.stem not in reviewed and not args.allow_unreviewed:
            print(f"unreviewed frame: {f.name}; review it or use --allow-unreviewed for exploration", file=sys.stderr)
            return 2
        try:
            boxes = check_label(label_path(labels_dir, f))
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
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
    if not val_set or val_set == set(per_tag):
        print("need distinct train and validation clip tags", file=sys.stderr)
        return 2

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

    for s, items in split.items():
        if not any(any(int(b[0]) == 0 for b in boxes) for _, boxes in items):
            print(f"{s} has no reviewed rat boxes", file=sys.stderr)
            return 2
        if not any(not boxes for _, boxes in items):
            print(f"{s} has no reviewed empty negatives", file=sys.stderr)
            return 2

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
            if f.name not in sources:
                print(f"missing augmentation source: {f.name}", file=sys.stderr)
                return 2
            s = sources[f.name]
            touches = {source_tag(tag_of(f.stem)), s.get("rat_source", ""), s.get("bg_source", "")}
            if touches & val_set:
                n_extra_dropped += 1
                continue
            try:
                boxes = check_label(label_path(el, f))
            except ValueError as exc:
                print(exc, file=sys.stderr)
                return 2
            split["train"].append((f, boxes))
            n_extra += 1

    names_by_split = {s: [f.name for f, _ in items] for s, items in split.items()}
    all_names = names_by_split["train"] + names_by_split["val"]
    if len(set(all_names)) != len(all_names):
        print("duplicate frame filename in dataset sources", file=sys.stderr)
        return 2

    # write
    if out.exists() or out.is_symlink():
        if not args.replace:
            print(f"output already exists: {out}; choose a new --out or pass --replace", file=sys.stderr)
            return 2
        if not out.is_dir() or out.is_symlink():
            print(f"--replace requires a real output directory: {out}", file=sys.stderr)
            return 2
        source_dirs = [frames_dir, labels_dir]
        source_dirs.extend(Path(part) for spec in args.extra for part in spec.split(":"))
        output_path = out.resolve()
        if any(source.resolve().is_relative_to(output_path) for source in source_dirs):
            print(f"refusing to replace {out}: it contains a source directory", file=sys.stderr)
            return 2
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
    manifest = {"gray": args.gray, "reviewed_only": not args.allow_unreviewed,
                "train_tags": sorted(set(per_tag) - val_set), "val_tags": val_tags,
                "train_frames": len(split["train"]), "val_frames": len(split["val"]),
                "train_empty": sum(not boxes for _, boxes in split["train"]),
                "val_empty": sum(not boxes for _, boxes in split["val"]),
                "extra_train_frames": n_extra, "frames": names_by_split}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

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
