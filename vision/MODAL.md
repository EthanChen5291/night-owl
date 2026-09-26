# One Modal training run

`modal_train.py` trains a candidate from `dataset/` on one L4 GPU. It runs for at most 60 minutes, with up to 4 CPUs and 16 GiB RAM. It creates an ephemeral Modal app run and no endpoint. Modal's published rates put that upper bound near $1.12 for GPU, CPU, and memory, before any storage or other charges: [pricing](https://modal.com/pricing).

Build `dataset/` with `make_dataset.py` after reviewing labels. The launcher checks `manifest.json`, matching images and labels, grayscale conversion, reviewed status, clip-level train/validation separation, rat boxes, and empty negative frames in each split. It accepts a dataset without person boxes but records that limit. Never mark an unreviewed label as reviewed to pass preflight.

From the repository root:

```sh
/Users/utsavsharma/miniconda3/bin/modal run vision/modal_train.py --dataset vision/dataset --dry-run
/Users/utsavsharma/miniconda3/bin/modal run vision/modal_train.py --dataset vision/dataset --out vision/runs/modal-rat --epochs 150 --batch 8
```

The full run uploads the dataset to a run-specific path in the `poc-rat-train-files` volume, trains YOLO11n at 416 pixels, downloads `best.pt`, `rat.onnx`, `results.csv`, `metrics.json`, a dataset snapshot, and a `training_report.json` compatible with `promote_model.py`, checks artifact hashes, then removes that run's remote files. The report includes PT and ONNX AP50, raw-output parity on held-out frames, dependency versions, and the dataset fingerprint. The ONNX file is a **candidate**. `promote_model.py` handles the event-level gate before replacing `pi/rat.onnx`.

If training or export fails, the launcher downloads any artifacts already committed and keeps the remote output path for recovery. It removes that path only after a complete download and checksum check. Use `--keep-remote` for remote debugging, then remove the run paths after recovery.
