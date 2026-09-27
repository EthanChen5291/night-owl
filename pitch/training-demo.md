# Training demo clip

[Current MP4, V2](out/barn-owl-training-demo-v2.mp4) · [preview](out/barn-owl-training-demo-v2-preview.jpg)

This 15.6-second, silent H.264 clip uses saved artifacts from the V3 room-lit plush detector run. It shows the real 150-epoch `metrics/mAP50(B)` trainer history, then exported ONNX inference on the recorded `zoom15_b` metal-table clip at 62–66.5 seconds. The bounding boxes and confidence labels are computed from the ONNX model on grayscale frames; the underlying camera image is shown in color. The crop is taken from each model box.

V2 closes with the matched square-416 CPU rat AP50 from `vision/HILL_CLIMB.md`: 0.943 on two fixed validation clips reused for recipe and checkpoint selection, then 0.870 on a one-time independent test of 186 reviewed frames. The fresh new-angle positive clip scored 0.844; the independent result missed the 0.90 target. The video does not read or predict on the independent recordings; those values are copied from the locked test report. It shows neither a GPU console recording nor physical Pi inference. Further training is under way.

[Historical V1 MP4](out/barn-owl-training-demo-v1.mp4) was rendered before the independent test. Its closing “independent scene test pending” caption is now stale. Use V2 for the current V3 result.

Inputs and SHA-256:

| Artifact | SHA-256 |
| --- | --- |
| `vision/runs/modal-rat-v3-expanded-20260926/results.csv` | `1451521c068fac0b0b18be6fd77b02ab1c9c115d6aee3bfa60ac8d70bd569959` |
| `vision/runs/modal-rat-v3-expanded-20260926/rat.onnx` | `3214f2a0dbe1699016b8f4e8aaa8d4c7c5eb3d5e365a07f26a2efbe13114672b` |
| `vision/clips/zoom15_b.mp4` | `d498ea78b27621d406fe2d64b3e8852477fb8229151fa21ceb674931f2124529` |
| `pitch/out/barn-owl-training-demo-v1.mp4` | `084eadc709d2e3506465d18642da89a8d12d9cf47c05c92151ff81cdd8984559` |
| `pitch/out/barn-owl-training-demo-v2.mp4` | `5e7a36bfda14e50bc38769dbb6865cac205a047db0de3d6518013687168fc1aa` |

The source is `pitch/make_training_video.py`. Run `vision/.venv/bin/python pitch/make_training_video.py --version v2` with `ffmpeg` available on `PATH`; `--version v1` reproduces the historical caption. V2 is 1280×720 at 15 fps, 464 KB. Update the captions and filename if a later candidate becomes the presentation model.
