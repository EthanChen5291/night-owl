#!/usr/bin/env python3
"""Train YOLO11n on reviewed grayscale clips and export a validated candidate ONNX."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parity(pt_path: Path, onnx_path: Path, val_images: list[Path], imgsz: int) -> dict:
    """Compare raw YOLO output on identical tensors, including node preprocessing."""
    import cv2
    import numpy as np
    import torch
    from ultralytics import YOLO
    from pi.detect import Detector

    ort_model = Detector(str(onnx_path), imgsz=imgsz, gray=True)
    pt_model = YOLO(str(pt_path)).model.cpu().eval()
    samples = []
    with torch.no_grad():
        for image in val_images[:5]:
            frame = cv2.imread(str(image), cv2.IMREAD_GRAYSCALE)
            if frame is None:
                raise RuntimeError(f"cannot read parity image {image}")
            x, _, _, _ = ort_model.preprocess(frame)
            pt_out = pt_model(torch.from_numpy(x))
            if isinstance(pt_out, (tuple, list)):
                pt_out = pt_out[0]
            pt_out = pt_out.detach().numpy()
            onnx_out = ort_model.sess.run(None, {ort_model.input_name: x})[0]
            if pt_out.shape != onnx_out.shape:
                raise RuntimeError(f"PT/ONNX output shape differs: {pt_out.shape} vs {onnx_out.shape}")
            diff = np.abs(pt_out - onnx_out)
            samples.append({"image": image.name, "max_abs": float(diff.max()),
                            "mean_abs": float(diff.mean())})
    max_abs = max(s["max_abs"] for s in samples)
    mean_abs = max(s["mean_abs"] for s in samples)
    return {"pass": max_abs <= 0.02 and mean_abs <= 0.001,
            "max_abs": max_abs, "max_mean_abs": mean_abs, "samples": samples}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="dataset/data.yaml")
    ap.add_argument("--model", default="yolo11n.pt")
    ap.add_argument("--imgsz", type=int, default=416)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--project", default="runs")
    ap.add_argument("--name", default="rat")
    ap.add_argument("--device", default=None)
    ap.add_argument("--allow-unreviewed", action="store_true",
                    help="explicit demo override for a dataset built with --allow-unreviewed")
    args = ap.parse_args(argv)
    data = Path(args.data).resolve()
    manifest_path = data.parent / "manifest.json"
    if not data.is_file() or not manifest_path.is_file():
        ap.error("dataset/data.yaml and dataset/manifest.json are required; run make_dataset.py")
    manifest = json.loads(manifest_path.read_text())
    if not manifest.get("gray"):
        ap.error("training requires grayscale data")
    if not manifest.get("reviewed_only") and not args.allow_unreviewed:
        ap.error("unreviewed labels require an explicit --allow-unreviewed override")
    if not manifest.get("train_tags") or not manifest.get("val_tags") or not manifest.get("train_empty") or not manifest.get("val_empty"):
        ap.error("dataset must have separate clip tags and negatives in both splits")
    run = Path(args.project) / args.name
    if run.exists() and any(run.iterdir()):
        ap.error(f"{run} already contains a run; choose a new --name to avoid stale weights and reports")

    from ultralytics import YOLO
    train_kw = dict(data=str(data), imgsz=args.imgsz, epochs=args.epochs, batch=args.batch,
                    project=args.project, name=args.name, exist_ok=True, plots=True, patience=20,
                    hsv_h=0.0, hsv_s=0.0, hsv_v=0.4, fliplr=0.5, mosaic=1.0, close_mosaic=10)
    if args.device:
        train_kw["device"] = args.device
    YOLO(args.model).train(**train_kw)
    best = run / "weights" / "best.pt"
    if not best.is_file():
        raise RuntimeError(f"missing best weights: {best}")

    model = YOLO(str(best))
    metrics = model.val(data=str(data), imgsz=args.imgsz, plots=False, verbose=False,
                        **({"device": args.device} if args.device else {}))
    ap50_by_class = {str(metrics.names[int(ci)]): float(score)
                     for ci, score in zip(metrics.box.ap_class_index, metrics.box.ap50)}
    rat_ap50 = ap50_by_class.get("rat")
    gate_a = rat_ap50 is not None and rat_ap50 > 0.9

    exported = Path(model.export(format="onnx", imgsz=args.imgsz, opset=12,
                                 simplify=True, dynamic=False))
    candidate = run / "candidate.onnx"
    if exported.resolve() != candidate.resolve():
        shutil.copy2(exported, candidate)
    val_images = sorted((data.parent / "images" / "val").glob("*.jpg"))
    val_images += sorted((data.parent / "images" / "val").glob("*.png"))
    if not val_images:
        raise RuntimeError("no held-out images for ONNX parity")
    parity_result = parity(best, candidate, val_images, args.imgsz)
    report = {"dataset_manifest_sha256": sha256(manifest_path), "candidate": str(candidate.resolve()),
              "candidate_sha256": sha256(candidate), "best_pt": str(best.resolve()),
              "reviewed_only": manifest["reviewed_only"],
              "rat_ap50": rat_ap50, "ap50_by_class": ap50_by_class,
              "map50_all": float(metrics.box.map50), "gate_a_pass": gate_a,
              "onnx_parity": parity_result, "train_args": vars(args)}
    report_path = run / "training_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"candidate: {candidate}\ntraining report: {report_path}\n"
          f"rat AP50: {rat_ap50}, gate A: {'PASS' if gate_a else 'FAIL'}\n"
          f"ONNX parity: {'PASS' if parity_result['pass'] else 'FAIL'}")
    return 0 if gate_a and parity_result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
