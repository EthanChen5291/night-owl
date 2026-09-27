# Modal training environment

NightOwl trained the plush-rat YOLO11n candidates on one Modal L4 at a time. Each job was capped at 3,600 seconds, used at most four CPUs and 16 GiB of memory, and had zero retries. The launcher creates no serving endpoint. At [Modal's listed rates](https://modal.com/pricing), one full-hour job is about $1.12 for those GPU, CPU, and memory limits, before storage or other charges.

The current results are in [V5 results](V5_RESULTS.md), [V5 formal event results](V5_FORMAL_EVENT_RESULTS.md), and [V6 results](V6_RESULTS.md). V5 remains a supervised lit-room candidate after its formal event test failed. The V6 recovery model also failed its predeclared development regression limits. Neither was promoted to `pi/rat.onnx`; no further GPU run is queued by this document.

## Inputs and reproducibility

`make_dataset.py` writes grayscale images repeated across three channels, matching Pi inference. Every selected image needs a reviewed YOLO label file. An empty file means a reviewer found neither a plush rat nor a person in the full frame. The manifest records source tags and keeps whole clips in either training or validation. Keep the source video, review markers, manifest, and image/label fingerprints with each run.

The generic `modal_train.py` launcher checks those inputs before upload. Run its dry preflight from the repository root with a reviewed dataset:

```sh
/Users/utsavsharma/miniconda3/bin/modal run vision/modal_train.py \
  --dataset vision/dataset_v5 --dry-run
```

This checks structure; it does not recreate V5's exact training recipe. The fixed V5 recipe, starting checkpoint, resolved arguments, and hashes are in `vision/runs/modal-rat-v5-20260927/` and [V5 results](V5_RESULTS.md). The V6 launcher and its rejected result have a separate record in `vision/runs/modal-rat-v6-20260927/` and [V6 results](V6_RESULTS.md). Do not treat the generic command defaults as either run's preregistered settings.

A full launcher run uploads a dataset to a run-specific path in the `poc-rat-train-files` volume, trains at square 416, and downloads the selected checkpoint, trainer and rat-best checkpoints, ONNX export, metrics, resolved arguments, checkpoint selection, dataset snapshot, and `training_report.json`. It verifies file hashes before removing remote outputs. If download or validation fails, it keeps the remote output path for recovery. `--keep-remote` also retains it deliberately.

The report compares PyTorch and ONNX with the same square-416 CPU input and records raw-output parity. Checkpoint scores on repeatedly used validation clips are development evidence. The selected ONNX remains a candidate even when box AP passes; an independent whole-video event test with reviewed push intervals and a separate no-plush clip is required before promotion. V5's such test failed. [RUNBOOK.md](RUNBOOK.md) lists the current gates and replay commands.
