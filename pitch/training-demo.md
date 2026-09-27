# Training demo clip

[MP4](out/barn-owl-training-demo-v1.mp4) · [preview](out/barn-owl-training-demo-preview.jpg)

This 15.6-second, silent H.264 clip uses saved artifacts from the V3 room-lit plush detector run. It shows the real 150-epoch `metrics/mAP50(B)` trainer history, then exported ONNX inference on the recorded `zoom15_b` metal-table clip at 62–66.5 seconds. The bounding boxes and confidence labels are computed from the ONNX model on grayscale frames; the underlying camera image is shown in color. The crop is taken from each model box.

The closing rat AP50 values come from the matched square-416 CPU verification in `vision/TRAINING_RESULTS.md`: 0.943 combined, 0.995 metal table, 0.817 floor. Both validation clips were reused during training-recipe and checkpoint selection. These figures are tuned validation, not a new independent test. The video does not use or predict on the reserved independent clips. It shows neither a GPU console recording nor physical Pi inference.

Inputs and SHA-256:

| Artifact | SHA-256 |
| --- | --- |
| `vision/runs/modal-rat-v3-expanded-20260926/results.csv` | `1451521c068fac0b0b18be6fd77b02ab1c9c115d6aee3bfa60ac8d70bd569959` |
| `vision/runs/modal-rat-v3-expanded-20260926/rat.onnx` | `3214f2a0dbe1699016b8f4e8aaa8d4c7c5eb3d5e365a07f26a2efbe13114672b` |
| `vision/clips/zoom15_b.mp4` | `d498ea78b27621d406fe2d64b3e8852477fb8229151fa21ceb674931f2124529` |
| `pitch/out/barn-owl-training-demo-v1.mp4` | `084eadc709d2e3506465d18642da89a8d12d9cf47c05c92151ff81cdd8984559` |

The source is `pitch/make_training_video.py`. Run it with `vision/.venv/bin/python` and `ffmpeg` available on `PATH`. The generated video is 1280×720 at 15 fps, 447 KB. Update its captions and filename if the final independent test changes the presentation story.
