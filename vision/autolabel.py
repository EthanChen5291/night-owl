#!/usr/bin/env python3
"""Zero-shot auto-labelling of ``frames/`` with YOLO-World, written as YOLO txt in ``labels/``.

YOLO-World takes the prompt ``["stuffed animal", "person"]``; prompt index 0 becomes class 0 (rat,
the Forum Novelties prop) and index 1 becomes class 1 (person). Boxes at or above ``--conf`` (0.25)
are kept; frames with nothing above it get an *empty* label file, which downstream means "negative"
until ``review.py`` says otherwise. Per-frame maxima go to ``labels/_autolabel.csv`` so the review
pass can be ordered by confidence (the low-confidence dark-floor frames are where the bias is, see
HANDOFF Q4).

Already-labelled frames are skipped unless ``--overwrite``; frames listed in ``labels/_reviewed.txt``
are never overwritten. ``--export-onnx pi/world_rat_person.onnx`` writes the same prompted model
as the zero-training fallback the Pi runs for the hour-6 gate.

Example::

    python3 autolabel.py --frames frames --labels labels --conf 0.25
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import CLASS_NAMES, append_csv_row, label_path, list_frames, write_labels

PROMPTS = ["stuffed animal", "person"]  # index == class id
AUTOLABEL_FIELDS = ["frame", "n_rat", "n_person", "max_conf_rat", "max_conf_person"]


def load_reviewed(labels_dir: Path) -> set[str]:
    p = labels_dir / "_reviewed.txt"
    if not p.is_file():
        return set()
    return {line.split("\t")[0].strip() for line in p.read_text().splitlines() if line.strip()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", default="frames")
    ap.add_argument("--labels", default="labels")
    ap.add_argument("--model", default="yolov8s-worldv2.pt", help="ultralytics YOLO-World weights (downloaded on first use)")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--iou", type=float, default=0.5, help="NMS IoU")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--device", default=None, help="e.g. mps, cpu, 0 (default: ultralytics picks)")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0, help="stop after N frames (smoke test)")
    ap.add_argument("--overwrite", action="store_true", help="relabel frames that already have a label file")
    ap.add_argument("--export-onnx", metavar="PATH", help="also export the prompted model to ONNX (416, opset 12)")
    args = ap.parse_args(argv)

    try:
        from ultralytics import YOLOWorld
    except ImportError:
        print("ultralytics is not installed: pip install ultralytics", file=sys.stderr)
        return 2

    frames_dir, labels_dir = Path(args.frames), Path(args.labels)
    labels_dir.mkdir(parents=True, exist_ok=True)
    reviewed = load_reviewed(labels_dir)

    model = YOLOWorld(args.model)
    model.set_classes(PROMPTS)

    if args.export_onnx:
        out = model.export(format="onnx", imgsz=416, opset=12, simplify=True)
        dst = Path(args.export_onnx)
        dst.parent.mkdir(parents=True, exist_ok=True)
        Path(out).replace(dst)
        print(f"exported fallback model -> {dst} (classes: {PROMPTS} -> {CLASS_NAMES})")

    frames = list_frames(frames_dir)
    todo = []
    for f in frames:
        lp = label_path(labels_dir, f)
        if f.stem in reviewed:
            continue
        if lp.is_file() and not args.overwrite:
            continue
        todo.append(f)
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(frames)} frames, {len(todo)} to label, {len(reviewed)} reviewed (kept)")
    if not todo:
        return 0

    n_pos = 0
    for i in range(0, len(todo), args.batch):
        chunk = todo[i : i + args.batch]
        results = model.predict([str(f) for f in chunk], conf=args.conf, iou=args.iou, imgsz=args.imgsz,
                                device=args.device, verbose=False)
        for f, r in zip(chunk, results):
            boxes = []
            maxc = [0.0, 0.0]
            cnt = [0, 0]
            if r.boxes is not None and len(r.boxes):
                cls = r.boxes.cls.tolist()
                conf = r.boxes.conf.tolist()
                xywhn = r.boxes.xywhn.tolist()
                for c, p, (cx, cy, w, h) in zip(cls, conf, xywhn):
                    c = int(c)
                    if c not in (0, 1):
                        continue
                    boxes.append([c, cx, cy, w, h])
                    maxc[c] = max(maxc[c], p)
                    cnt[c] += 1
            write_labels(label_path(labels_dir, f), boxes)
            append_csv_row(labels_dir / "_autolabel.csv", AUTOLABEL_FIELDS, {
                "frame": f.name, "n_rat": cnt[0], "n_person": cnt[1],
                "max_conf_rat": f"{maxc[0]:.3f}", "max_conf_person": f"{maxc[1]:.3f}"})
            n_pos += 1 if cnt[0] else 0
        print(f"  {min(i + args.batch, len(todo))}/{len(todo)}  frames with a rat so far: {n_pos}", flush=True)

    print(f"done: {len(todo)} labelled, {n_pos} with at least one rat box ({100 * n_pos / len(todo):.0f}%)")
    print("next: python3 review.py  (then prune.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
