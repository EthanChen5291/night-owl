#!/usr/bin/env python3
"""Train one reviewed YOLO11n candidate on one Modal L4 and download its artifacts.

Run from the repository root:

    modal run vision/modal_train.py --dataset vision/dataset --out vision/runs/modal-rat

Use ``--dry-run`` to check the dataset without uploading data or starting a GPU.
This is an ephemeral app run, not a deployment or a serving endpoint.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import uuid
import csv
from pathlib import Path

import modal


APP_NAME = "poc-rat-train"
VOLUME_NAME = "poc-rat-train-files"
IMAGE_SIZE = 416
MAX_EPOCHS = 200
GPU_SECONDS = 3600
PACKAGES = (
    "torch==2.8.0",
    "torchvision==0.23.0",
    "ultralytics==8.4.163",
    "onnx==1.19.0",
    "onnxslim==0.1.76",
    "onnxruntime==1.22.1",
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1", "libglib2.0-0")
    .uv_pip_install(*PACKAGES)
    .env({"YOLO_CONFIG_DIR": "/tmp/ultralytics", "WANDB_DISABLED": "true"})
)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
app = modal.App(APP_NAME)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_dataset(dataset: Path) -> dict:
    """Reject unreviewed labels, invalid boxes, or frame overlap before upload."""
    dataset = dataset.resolve()
    manifest_path = dataset / "manifest.json"
    yaml_path = dataset / "data.yaml"
    if not manifest_path.is_file() or not yaml_path.is_file():
        raise ValueError("dataset needs manifest.json and data.yaml from make_dataset.py")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("reviewed_only") is not True or manifest.get("gray") is not True:
        raise ValueError("dataset must contain reviewed-only grayscale frames")
    train_tags = set(manifest.get("train_tags", []))
    val_tags = set(manifest.get("val_tags", []))
    if not train_tags or not val_tags or train_tags & val_tags:
        raise ValueError("train and validation need distinct whole-clip tags")
    yaml = yaml_path.read_text()
    if not re.search(r"(?m)^nc:\s*2\s*$", yaml) or not re.search(r"(?m)^\s*0:\s*rat\s*$", yaml) or not re.search(r"(?m)^\s*1:\s*person\s*$", yaml):
        raise ValueError("data.yaml must name class 0 rat and class 1 person")
    summary = {"train": {}, "val": {}}
    all_names: set[str] = set()
    fingerprint = hashlib.sha256()
    for split in ("train", "val"):
        img_dir = dataset / "images" / split
        label_dir = dataset / "labels" / split
        expected = manifest.get("frames", {}).get(split)
        if not isinstance(expected, list) or not expected:
            raise ValueError(f"manifest has no {split} frame list")
        images = sorted(p for p in img_dir.iterdir() if p.is_file())
        names = {p.name for p in images}
        if len(names) != len(expected) or names != set(expected):
            raise ValueError(f"{split} image files differ from manifest")
        if all_names & names:
            raise ValueError("a frame filename occurs in both splits")
        all_names |= names
        expected_labels = {Path(n).stem + ".txt" for n in names}
        labels = {p.name for p in label_dir.iterdir() if p.is_file()}
        if labels != expected_labels:
            raise ValueError(f"{split} labels do not match images")
        counts = {"frames": len(images), "empty": 0, "rat_boxes": 0, "person_boxes": 0}
        for img in images:
            if img.is_symlink() or img.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                raise ValueError(f"unsupported image: {img}")
            label = label_dir / (img.stem + ".txt")
            if label.is_symlink():
                raise ValueError(f"symlink label: {label}")
            lines = label.read_text().splitlines()
            if not lines:
                counts["empty"] += 1
            for line in lines:
                values = line.split()
                if len(values) != 5 or values[0] not in {"0", "1"}:
                    raise ValueError(f"invalid class or box in {label}")
                try:
                    cx, cy, w, h = (float(x) for x in values[1:])
                except ValueError as exc:
                    raise ValueError(f"non-numeric box in {label}") from exc
                if not all(map(math.isfinite, (cx, cy, w, h))) or not (0 < w <= 1 and 0 < h <= 1 and 0 <= cx - w / 2 and cx + w / 2 <= 1 and 0 <= cy - h / 2 and cy + h / 2 <= 1):
                    raise ValueError(f"out-of-bounds box in {label}")
                counts["rat_boxes" if values[0] == "0" else "person_boxes"] += 1
            for path in (img, label):
                fingerprint.update(str(path.relative_to(dataset)).encode())
                fingerprint.update(bytes.fromhex(sha256(path)))
        if counts["rat_boxes"] == 0 or counts["empty"] == 0:
            raise ValueError(f"{split} needs reviewed rat boxes and empty negative frames")
        if counts["frames"] != manifest.get(f"{split}_frames") or counts["empty"] != manifest.get(f"{split}_empty"):
            raise ValueError(f"{split} counts differ from manifest")
        summary[split] = counts
    summary["train_tags"] = sorted(train_tags)
    summary["val_tags"] = sorted(val_tags)
    summary["dataset_sha256"] = fingerprint.hexdigest()
    summary["person_label_limit"] = summary["train"]["person_boxes"] == 0 or summary["val"]["person_boxes"] == 0
    return summary


def class_ap50(metrics) -> dict[str, float | None]:
    indices = [int(x) for x in metrics.box.ap_class_index]
    values = [float(x) for x in metrics.box.ap50]
    by_class = dict(zip(indices, values))
    return {"rat": by_class.get(0), "person": by_class.get(1)}


def raw_onnx_parity(best: Path, onnx: Path, dataset: Path) -> dict:
    """Compare PT and ONNX tensors after the same grayscale letterbox used on the Pi."""
    import cv2
    import numpy as np
    import onnxruntime as ort
    import torch
    from ultralytics import YOLO

    session = ort.InferenceSession(str(onnx), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    pytorch = YOLO(str(best)).model.cpu().eval()
    images = sorted((dataset / "images" / "val").iterdir())
    if not images:
        raise ValueError("no validation images for ONNX parity")
    samples = []
    with torch.no_grad():
        for path in images[:5]:
            gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if gray is None:
                raise ValueError(f"cannot decode {path}")
            height, width = gray.shape
            scale = min(IMAGE_SIZE / height, IMAGE_SIZE / width)
            new_width, new_height = max(1, round(width * scale)), max(1, round(height * scale))
            resized = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_LINEAR if scale > 1 else cv2.INTER_AREA)
            x0, y0 = (IMAGE_SIZE - new_width) // 2, (IMAGE_SIZE - new_height) // 2
            canvas = np.full((IMAGE_SIZE, IMAGE_SIZE), 114, dtype=np.uint8)
            canvas[y0:y0 + new_height, x0:x0 + new_width] = resized
            tensor = np.ascontiguousarray(np.repeat(canvas[None], 3, axis=0), dtype=np.float32)[None] / 255.0
            pt = pytorch(torch.from_numpy(tensor))
            if isinstance(pt, (tuple, list)):
                pt = pt[0]
            pt = pt.numpy()
            exported = session.run(None, {input_name: tensor})[0]
            if pt.shape != exported.shape:
                raise ValueError(f"output shapes differ on {path.name}: {pt.shape} vs {exported.shape}")
            diff = np.abs(pt - exported)
            samples.append({"frame": path.name, "max_abs": float(diff.max()), "mean_abs": float(diff.mean())})
    max_abs = max(sample["max_abs"] for sample in samples)
    max_mean = max(sample["mean_abs"] for sample in samples)
    return {"pass": max_abs <= 0.02 and max_mean <= 0.001, "max_abs": max_abs,
            "max_mean_abs": max_mean, "samples": samples}


@app.function(image=image, cpu=1, timeout=120)
def check_image() -> dict:
    """Build and import the training image without allocating a GPU."""
    import cv2
    import onnx
    import onnxruntime
    import torch
    import ultralytics

    versions = {"cv2": cv2.__version__, "onnx": onnx.__version__,
                "onnxruntime": onnxruntime.__version__, "torch": torch.__version__,
                "ultralytics": ultralytics.__version__}
    print(json.dumps(versions, indent=2))
    return versions


@app.function(image=image, gpu="L4", cpu=4, memory=16384, timeout=GPU_SECONDS, retries=0, volumes={"/data": volume})
def train_candidate(run_id: str, epochs: int, batch: int, expected_sha: str) -> dict:
    import platform
    import torch
    import ultralytics
    import onnxruntime
    from ultralytics import YOLO

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("expected exactly one CUDA GPU")
    root = Path("/data")
    dataset = root / "inputs" / run_id
    out = root / "outputs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    summary = validate_dataset(dataset)
    if summary["dataset_sha256"] != expected_sha:
        raise ValueError("uploaded dataset checksum differs from preflight")
    data_yaml = Path("/tmp") / f"rat-{run_id}.yaml"
    data_yaml.write_text(
        f"path: {dataset}\ntrain: images/train\nval: images/val\nnc: 2\nnames:\n  0: rat\n  1: person\n"
    )
    work = Path("/tmp") / f"rat-{run_id}"
    work.mkdir()
    pretrained = YOLO("yolo11n.pt")
    pretrained_hash = sha256(Path("yolo11n.pt"))
    pretrained.train(
        data=str(data_yaml), imgsz=IMAGE_SIZE, epochs=epochs, batch=batch,
        device=0, workers=4, project=str(work), name="train", exist_ok=False,
        patience=epochs, plots=False, seed=0, deterministic=True, cache=False,
        optimizer="AdamW", lr0=0.0003, lrf=0.01,
        hsv_h=0.0, hsv_s=0.0, hsv_v=0.15, fliplr=0.5,
        mosaic=0.0, close_mosaic=0, scale=0.15, translate=0.05,
    )
    best = work / "train" / "weights" / "best.pt"
    if not best.is_file():
        raise RuntimeError("training did not produce best.pt")
    shutil.copy2(best, out / "best.pt")
    results_csv = work / "train" / "results.csv"
    epochs_completed = None
    if results_csv.is_file():
        shutil.copy2(results_csv, out / "results.csv")
        with results_csv.open(newline="") as handle:
            epochs_completed = sum(1 for _ in csv.DictReader(handle))
    volume.commit()  # Keep the trained checkpoint if validation or export fails.
    model = YOLO(str(best))
    pt_metrics = model.val(data=str(data_yaml), imgsz=IMAGE_SIZE, batch=batch, device=0, plots=False, verbose=False)
    export_path = Path(model.export(format="onnx", imgsz=IMAGE_SIZE, opset=12, simplify=True, dynamic=False, device=0))
    shutil.copy2(export_path, out / "rat.onnx")
    volume.commit()  # Keep the candidate if ONNX validation fails.
    onnx_metrics = YOLO(str(out / "rat.onnx")).val(data=str(data_yaml), imgsz=IMAGE_SIZE, batch=batch, device="cpu", plots=False, verbose=False)
    square_args = dict(data=str(data_yaml), imgsz=IMAGE_SIZE, batch=1, rect=False,
                       conf=0.001, iou=0.7, max_det=300, device="cpu",
                       plots=False, verbose=False)
    square_pt_metrics = YOLO(str(best)).val(**square_args)
    square_onnx_metrics = YOLO(str(out / "rat.onnx")).val(**square_args)
    parity = raw_onnx_parity(best, out / "rat.onnx", dataset)
    pt_ap = class_ap50(pt_metrics)
    onnx_ap = class_ap50(onnx_metrics)
    square_pt_ap = class_ap50(square_pt_metrics)
    square_onnx_ap = class_ap50(square_onnx_metrics)
    rat_delta = None if square_pt_ap["rat"] is None or square_onnx_ap["rat"] is None else abs(square_pt_ap["rat"] - square_onnx_ap["rat"])
    report = {
        "run_id": run_id, "dataset": summary, "model": "yolo11n.pt",
        "pretrained_sha256": pretrained_hash, "image_size": IMAGE_SIZE,
        "epochs_requested": epochs, "epochs_completed": epochs_completed, "batch": batch, "seed": 0,
        "training_recipe": {"patience": epochs, "optimizer": "AdamW", "lr0": 0.0003,
                            "lrf": 0.01, "mosaic": 0.0, "scale": 0.15,
                            "translate": 0.05, "hsv_v": 0.15, "fliplr": 0.5},
        "packages": {"torch": torch.__version__, "ultralytics": ultralytics.__version__, "onnxruntime": onnxruntime.__version__},
        "platform": platform.platform(), "gpu": torch.cuda.get_device_name(0),
        "pt_map50": float(pt_metrics.box.map50), "pt_ap50": pt_ap,
        "onnx_map50": float(onnx_metrics.box.map50), "onnx_ap50": onnx_ap,
        "matched_shape": {"protocol": "square 416, batch 1, rect=False, conf=0.001, iou=0.7, max_det=300",
                          "pt_map50": float(square_pt_metrics.box.map50), "pt_ap50": square_pt_ap,
                          "onnx_map50": float(square_onnx_metrics.box.map50), "onnx_ap50": square_onnx_ap},
        "rat_ap50_delta": rat_delta,
        "rat_gate_pass": square_onnx_ap["rat"] is not None and square_onnx_ap["rat"] > 0.9,
        "onnx_parity": parity,
        "onnx_parity_pass": parity["pass"] and rat_delta is not None and rat_delta <= 0.02,
        "event_gate": "not_run; requires reviewed push times and negatives reel",
        "artifacts_sha256": {name: sha256(out / name) for name in ("best.pt", "rat.onnx")},
    }
    (out / "metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    volume.commit()
    return report


@app.local_entrypoint()
def main(dataset: str = "vision/dataset", out: str = "vision/runs/modal-rat", epochs: int = 150,
         batch: int = 8, dry_run: bool = False, keep_remote: bool = False):
    if not (1 <= epochs <= MAX_EPOCHS) or not (1 <= batch <= 32):
        raise ValueError("epochs must be 1..200 and batch must be 1..32")
    source = Path(dataset).resolve()
    destination = Path(out).resolve()
    summary = validate_dataset(source)
    print(json.dumps(summary, indent=2))
    if dry_run:
        print("Preflight passed. No upload or GPU run started.")
        return
    if destination.is_file() or (destination.is_dir() and any(destination.iterdir())):
        raise FileExistsError(f"output directory is not empty: {destination}")
    run_id = uuid.uuid4().hex[:12]
    input_path = f"inputs/{run_id}"
    output_path = f"outputs/{run_id}"
    print(f"Uploading reviewed dataset to Modal volume {VOLUME_NAME}/{input_path}")
    download_verified = False
    try:
        with volume.batch_upload() as batch_upload:
            batch_upload.put_directory(str(source), f"/{input_path}")
        remote_error = None
        try:
            report = train_candidate.remote(run_id, epochs, batch, summary["dataset_sha256"])
        except Exception as exc:
            remote_error = exc
            report = None
        destination.mkdir(parents=True, exist_ok=True)
        try:
            entries = volume.listdir(output_path, recursive=True)
        except Exception:
            if remote_error is None:
                raise
            entries = []
        for entry in entries:
            if entry.type != modal.volume.FileEntryType.FILE:
                continue
            rel = Path(entry.path.lstrip("/")).relative_to(output_path)
            local = destination / rel
            local.parent.mkdir(parents=True, exist_ok=True)
            with local.open("wb") as handle:
                for chunk in volume.read_file(entry.path):
                    handle.write(chunk)
        if remote_error is not None:
            raise RuntimeError(f"Modal training failed; downloaded any committed artifacts to {destination}") from remote_error
        for name, expected in report["artifacts_sha256"].items():
            if sha256(destination / name) != expected:
                raise RuntimeError(f"downloaded {name} checksum differs from Modal output")
        snapshot = destination / "dataset"
        shutil.copytree(source, snapshot)
        snapshot_yaml = snapshot / "data.yaml"
        snapshot_yaml.write_text(re.sub(r"(?m)^path:.*$", f"path: {snapshot}", snapshot_yaml.read_text()))
        if validate_dataset(snapshot)["dataset_sha256"] != summary["dataset_sha256"]:
            raise RuntimeError("saved dataset snapshot differs from training input")
        parity_report = {
            **report["onnx_parity"],
            "raw_pass": report["onnx_parity"]["pass"],
            "rat_ap50_delta": report["rat_ap50_delta"],
            "ap50_delta_pass": report["rat_ap50_delta"] is not None and report["rat_ap50_delta"] <= 0.02,
            "pass": report["onnx_parity_pass"],
        }
        training_report = {
            "dataset_manifest_sha256": sha256(source / "manifest.json"),
            "candidate": str((destination / "rat.onnx").resolve()),
            "candidate_sha256": report["artifacts_sha256"]["rat.onnx"],
            "best_pt": str((destination / "best.pt").resolve()),
            "reviewed_only": True,
            "rat_ap50": report["matched_shape"]["onnx_ap50"]["rat"],
            "ap50_by_class": report["matched_shape"]["onnx_ap50"],
            "map50_all": report["matched_shape"]["onnx_map50"],
            "gate_a_pass": report["rat_gate_pass"],
            "onnx_parity": parity_report,
            "train_args": {"model": report["model"], "imgsz": IMAGE_SIZE,
                           "epochs": epochs, "epochs_completed": report["epochs_completed"],
                           "batch": batch, "device": "L4", "seed": 0,
                           **report["training_recipe"]},
        }
        (destination / "training_report.json").write_text(json.dumps(training_report, indent=2) + "\n")
        download_verified = True
        print(f"Candidate saved in {destination}")
        print(json.dumps({k: report[k] for k in ("pt_ap50", "onnx_ap50", "rat_gate_pass", "onnx_parity_pass", "event_gate")}, indent=2))
    finally:
        if not keep_remote:
            volume.remove_file(input_path, recursive=True)
            if download_verified:
                volume.remove_file(output_path, recursive=True)
                print(f"Removed this run's inputs and outputs from {VOLUME_NAME}")
            else:
                print(f"Remote recovery path retained: {VOLUME_NAME}/{output_path}")
