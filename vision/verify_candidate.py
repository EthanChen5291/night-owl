#!/usr/bin/env python3
"""Independently score a candidate on the fixed reviewed validation clips.

The output is diagnostic only. AP uses the same square-416 CPU protocol as
modal_train.py; event recall still needs independently reviewed push times.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

from common import tag_of
from eval_clips import class_ap50
from pi.detect import Detector, apply_rules, iou_xywh


IMGSZ = 416
CONF_AP = 0.001
IOU_NMS = 0.7
MAX_DET = 300
RUNTIME_CONF = 0.5
FLOOR_Y = 0.0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory(dataset: Path) -> tuple[dict, dict[str, list[Path]]]:
    manifest = json.loads((dataset / "manifest.json").read_text())
    train_tags = set(manifest["train_tags"])
    val_tags = set(manifest["val_tags"])
    if not manifest.get("reviewed_only") or not manifest.get("gray") or not train_tags or not val_tags or train_tags & val_tags:
        raise ValueError("dataset needs reviewed grayscale data and disjoint whole-clip splits")
    train_names = set(manifest["frames"]["train"])
    expected = set(manifest["frames"]["val"])
    if train_names & expected or any(tag_of(Path(name).stem) not in train_tags for name in train_names):
        raise ValueError("train manifest contains a held-out frame or clip")
    images = sorted((dataset / "images/val").glob("*.jpg"))
    if {p.name for p in images} != expected or len(images) != len(expected):
        raise ValueError("validation images differ from the manifest")
    by_tag: dict[str, list[Path]] = defaultdict(list)
    for image in images:
        tag = tag_of(image.stem)
        if tag not in val_tags or not (dataset / "labels/val" / f"{image.stem}.txt").is_file():
            raise ValueError(f"unlisted clip or missing label for {image.name}")
        by_tag[tag].append(image)
    if set(by_tag) != val_tags:
        raise ValueError("a validation clip has no frames")
    return manifest, dict(by_tag)


def xywh_to_xyxy(values: list[float], width: int, height: int) -> list[float]:
    cx, cy, w, h = values
    return [(cx - w / 2) * width, (cy - h / 2) * height,
            (cx + w / 2) * width, (cy + h / 2) * height]


def box_iou(a: list[float], b: list[float]) -> float:
    aa = [a[0], a[1], a[2] - a[0], a[3] - a[1]]
    bb = [b[0], b[1], b[2] - b[0], b[3] - b[1]]
    return iou_xywh(aa, bb)


def match_counts(frames: list[dict], threshold: float) -> dict:
    tp = fp = gt_total = 0
    for frame in frames:
        gt = [g for g in frame["gt"] if g["cls"] == 0]
        gt_total += len(gt)
        used: set[int] = set()
        candidates = sorted(
            (p for p in frame["pred"] if p["cls"] == 0 and p["conf"] >= threshold),
            key=lambda p: -p["conf"],
        )
        for candidate in candidates:
            possible = [(box_iou(candidate["xyxy"], g["xyxy"]), i)
                        for i, g in enumerate(gt) if i not in used]
            if possible and max(possible)[0] >= 0.5:
                used.add(max(possible)[1])
                tp += 1
            else:
                fp += 1
    return {"tp": tp, "fp": fp, "gt": gt_total,
            "recall": tp / gt_total if gt_total else None,
            "precision": tp / (tp + fp) if tp + fp else None}


def score_models(dataset: Path, by_tag: dict[str, list[Path]], pt: Path, onnx: Path,
                 scratch: Path) -> dict:
    from ultralytics import YOLO

    scores: dict = {"combined": {}, "clips": {}}
    for tag, images in [("combined", sum(by_tag.values(), [])), *by_tag.items()]:
        root = scratch / tag
        (root / "images/val").mkdir(parents=True)
        (root / "labels/val").mkdir(parents=True)
        for image in images:
            shutil.copy2(image, root / "images/val" / image.name)
            label = dataset / "labels/val" / f"{image.stem}.txt"
            shutil.copy2(label, root / "labels/val" / label.name)
        yaml = root / "data.yaml"
        yaml.write_text(f"path: {root}\ntrain: images/val\nval: images/val\nnc: 2\nnames:\n  0: rat\n  1: person\n")
        result = {"frames": len(images)}
        for kind, model_path in (("pt", pt), ("onnx", onnx)):
            metrics = YOLO(str(model_path)).val(
                data=str(yaml), imgsz=IMGSZ, batch=1, rect=False,
                conf=CONF_AP, iou=IOU_NMS, max_det=MAX_DET,
                device="cpu", plots=False, verbose=False,
                project=str(scratch), name=f"{tag}-{kind}", exist_ok=True,
            )
            result[kind] = {"map50": float(metrics.box.map50),
                            "ap50": class_ap50(metrics)}
        if tag == "combined":
            scores["combined"] = result
        else:
            scores["clips"][tag] = result
    return scores


def predict_frames(dataset: Path, by_tag: dict[str, list[Path]], onnx: Path) -> list[dict]:
    import cv2
    from ultralytics import YOLO

    model = YOLO(str(onnx))
    records = []
    for tag, images in by_tag.items():
        for image in images:
            frame = cv2.imread(str(image))
            height, width = frame.shape[:2]
            result = model.predict(source=str(image), imgsz=IMGSZ, batch=1,
                                   rect=False, conf=CONF_AP, iou=IOU_NMS,
                                   max_det=MAX_DET, device="cpu", verbose=False)[0]
            labels = []
            for line in (dataset / "labels/val" / f"{image.stem}.txt").read_text().splitlines():
                cls, *values = map(float, line.split())
                labels.append({"cls": int(cls), "xyxy": xywh_to_xyxy(values, width, height)})
            predictions = [{"cls": int(box.cls.item()), "conf": float(box.conf.item()),
                            "xyxy": box.xyxy[0].tolist()} for box in result.boxes]
            for label in labels:
                same = [p for p in predictions if p["cls"] == label["cls"]]
                label["best_iou"] = max((box_iou(label["xyxy"], p["xyxy"]) for p in same), default=0.0)
                label["best_match_conf"] = max(
                    (p["conf"] for p in same if box_iou(label["xyxy"], p["xyxy"]) >= 0.5),
                    default=0.0,
                )
            for prediction in predictions:
                same = [g for g in labels if g["cls"] == prediction["cls"]]
                prediction["best_iou"] = max((box_iou(prediction["xyxy"], g["xyxy"]) for g in same), default=0.0)
            records.append({"image": image.name, "clip": tag, "width": width, "height": height,
                            "gt": labels, "pred": predictions})
    return records


def runtime_counts(dataset: Path, onnx: Path, frames: list[dict]) -> dict:
    import cv2

    detector = Detector(str(onnx), imgsz=IMGSZ, gray=True,
                        conf=RUNTIME_CONF, iou=0.45, names=["rat", "person"])
    output = {}
    for tag in sorted({f["clip"] for f in frames}):
        total = kept = dropped = tp = fp = gt_total = 0
        for frame in (f for f in frames if f["clip"] == tag):
            width, height = frame["width"], frame["height"]
            image = cv2.imread(str(dataset / "images/val" / frame["image"]))
            dets = detector.infer(image)
            rats, _ = apply_rules(dets, floor_y=FLOOR_Y)
            n_rats = sum(d.cls == "rat" for d in dets)
            total += n_rats
            kept += len(rats)
            dropped += n_rats - len(rats)
            gt = [g for g in frame["gt"] if g["cls"] == 0]
            gt_total += len(gt)
            used: set[int] = set()
            for rat in rats:
                p = [rat.x * width, rat.y * height,
                     (rat.x + rat.w) * width, (rat.y + rat.h) * height]
                options = [(box_iou(p, g["xyxy"]), i) for i, g in enumerate(gt) if i not in used]
                if options and max(options)[0] >= 0.5:
                    used.add(max(options)[1])
                    tp += 1
                else:
                    fp += 1
        output[tag] = {"rat_proposals": total, "rat_kept": kept,
                       "rat_suppressed": dropped, "matched_rat": tp,
                       "unmatched_rat": fp, "gt_rat": gt_total}
    return output


def contact_sheets(dataset: Path, frames: list[dict], output: Path) -> None:
    import cv2
    import numpy as np

    font = cv2.FONT_HERSHEY_SIMPLEX
    for tag in sorted({f["clip"] for f in frames}):
        tiles = []
        for record in (f for f in frames if f["clip"] == tag):
            frame = cv2.imread(str(dataset / "images/val" / record["image"]))
            for box in record["gt"]:
                x0, y0, x1, y1 = map(int, box["xyxy"])
                cv2.rectangle(frame, (x0, y0), (x1, y1),
                              (0, 220, 0) if box["cls"] == 0 else (220, 130, 0), 2)
            for box in record["pred"]:
                if box["conf"] < 0.05:
                    continue
                x0, y0, x1, y1 = map(int, box["xyxy"])
                color = (20, 20, 255) if box["cls"] == 0 else (255, 50, 50)
                cv2.rectangle(frame, (x0, y0), (x1, y1), color, 1)
                cv2.putText(frame, f"{'R' if box['cls'] == 0 else 'P'}{box['conf']:.2f}/{box['best_iou']:.2f}",
                            (max(0, x0), max(14, y0 - 3)), font, .45, color, 1)
            tile = cv2.resize(frame, (365, 274))
            header = np.full((38, 365, 3), 255, dtype=np.uint8)
            rats = [g for g in record["gt"] if g["cls"] == 0]
            label = record["image"] + " | " + ", ".join(f"GT IoU {g['best_iou']:.2f} @ {g['best_match_conf']:.2f}" for g in rats)
            cv2.putText(header, label[:49], (4, 23), font, .38, (0, 0, 0), 1)
            tiles.append(np.concatenate([header, tile], axis=0))
        blank = np.full_like(tiles[0], 255)
        rows = []
        for i in range(0, len(tiles), 3):
            row = tiles[i:i + 3]
            rows.append(np.concatenate(row + [blank] * (3 - len(row)), axis=1))
        cv2.imwrite(str(output / f"{tag}_contact.jpg"), np.concatenate(rows, axis=0),
                    [cv2.IMWRITE_JPEG_QUALITY, 85])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--pt", type=Path, required=True)
    parser.add_argument("--onnx", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    dataset, pt, onnx, output = (p.resolve() for p in (args.dataset, args.pt, args.onnx, args.out_dir))
    manifest, by_tag = inventory(dataset)
    import ultralytics
    import onnxruntime

    if ultralytics.__version__ != "8.4.163":
        raise RuntimeError(f"expected Modal Ultralytics 8.4.163, found {ultralytics.__version__}")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="poc-rat-verify-") as tmp:
        scores = score_models(dataset, by_tag, pt, onnx, Path(tmp))
    frames = predict_frames(dataset, by_tag, onnx)
    contact_sheets(dataset, frames, output)
    (output / "per_frame_predictions.json").write_text(json.dumps(frames, indent=2) + "\n")
    by_clip = {tag: [f for f in frames if f["clip"] == tag] for tag in by_tag}
    report = {
        "status": "DIAGNOSTIC_ONLY",
        "protocol": {"imgsz": IMGSZ, "batch": 1, "rect": False,
                     "conf": CONF_AP, "iou": IOU_NMS, "max_det": MAX_DET, "device": "cpu"},
        "packages": {"ultralytics": ultralytics.__version__, "onnxruntime": onnxruntime.__version__},
        "dataset_manifest_sha256": sha256(dataset / "manifest.json"),
        "train_tags": manifest["train_tags"], "val_tags": manifest["val_tags"],
        "pt_sha256": sha256(pt), "onnx_sha256": sha256(onnx),
        "scores": scores,
        "threshold_counts": {
            tag: {str(t): match_counts(records, t) for t in (0.5, 0.3, 0.1, 0.05, 0.01, 0.001)}
            for tag, records in {"combined": frames, **by_clip}.items()
        },
        "runtime_conf_0_5_floor_y_0": runtime_counts(dataset, onnx, frames),
    }
    (output / "verification_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"scores": scores, "runtime": report["runtime_conf_0_5_floor_y_0"]}, indent=2))


if __name__ == "__main__":
    main()
