#!/usr/bin/env python3
"""Measure a trained candidate on each whole held-out clip separately."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from common import tag_of


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def class_ap50(metrics) -> dict:
    found = {int(cls): float(score) for cls, score in zip(metrics.box.ap_class_index, metrics.box.ap50)}
    return {"rat": found.get(0), "person": found.get(1)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="saved dataset snapshot")
    parser.add_argument("--pt", type=Path, required=True, help="trained best.pt")
    parser.add_argument("--onnx", type=Path, required=True, help="exported candidate ONNX")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    dataset = args.dataset.resolve()
    manifest_path = dataset / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    val_tags = manifest["val_tags"]
    if len(val_tags) < 1 or set(val_tags) & set(manifest["train_tags"]):
        parser.error("manifest needs separate validation clip tags")

    from ultralytics import YOLO

    result = {
        "dataset_manifest_sha256": digest(manifest_path),
        "pt_sha256": digest(args.pt), "onnx_sha256": digest(args.onnx),
        "clips": {},
    }
    with tempfile.TemporaryDirectory(prefix="poc-rat-clip-eval-") as temp:
        scratch = Path(temp)
        images_by_tag = {tag: [] for tag in val_tags}
        for image in sorted((dataset / "images" / "val").iterdir()):
            tag = tag_of(image.stem)
            if tag not in images_by_tag:
                raise ValueError(f"validation image {image.name} has unknown clip tag {tag}")
            images_by_tag[tag].append(image)
        for tag, images in images_by_tag.items():
            if not images:
                raise ValueError(f"no validation frames for {tag}")
            clip_root = scratch / tag
            clip_images = clip_root / "images" / "val"
            clip_labels = clip_root / "labels" / "val"
            clip_images.mkdir(parents=True)
            clip_labels.mkdir(parents=True)
            box_counts = {"rat": 0, "person": 0}
            for image in images:
                label = dataset / "labels" / "val" / (image.stem + ".txt")
                shutil.copy2(image, clip_images / image.name)
                shutil.copy2(label, clip_labels / label.name)
                for line in label.read_text().splitlines():
                    box_counts["rat" if line.split()[0] == "0" else "person"] += 1
            yaml = clip_root / "data.yaml"
            yaml.write_text(f"path: {clip_root}\ntrain: images/val\nval: images/val\nnc: 2\nnames:\n  0: rat\n  1: person\n")
            scores = {}
            for kind, model_path in (("pt", args.pt), ("onnx", args.onnx)):
                metrics = YOLO(str(model_path)).val(
                    data=str(yaml), imgsz=416, batch=1, rect=False,
                    conf=0.001, iou=0.7, max_det=300, device="cpu", plots=False,
                    verbose=False, project=str(scratch), name=f"{tag}-{kind}", exist_ok=True,
                )
                scores[kind] = {"map50": float(metrics.box.map50), "ap50": class_ap50(metrics)}
            result["clips"][tag] = {"frames": len(images), "boxes": box_counts, **scores}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
