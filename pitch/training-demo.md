# V4 training demo clip (dated)

[V3 MP4](out/barn-owl-training-demo-v3.mp4) · [preview](out/barn-owl-training-demo-v3-preview.jpg)

This 15.6-second, silent H.264 clip uses the saved 150-epoch V4 training log and exported V4 ONNX model. The animated curve is `metrics/mAP50(B)` from `results.csv`, covering both rat and person. The camera segment is the original room-lit `zoom15_b` metal-table video at 62–66.5 seconds. Each rat box and crop comes from V4 ONNX inference on a grayscale copy of that frame at confidence .70. The underlying camera frame remains in color. `zoom15_b` was reused for model selection, so these images are a demonstration, not independent evidence.

The closing rat AP50 figures come from matched square-416 CPU verification. **.958** is tuned validation on 49 frames reused for checkpoint selection. **.926** is the locked V4 candidate on 59 reserved frames from four previously unused clips, with ONNX SHA256 `fb557bd9c1dafa7466a45afb50ac47668550a666a44f1791af714011a0bf1b27`. Those clips share the table, camera, and capture session with training recordings. AP50 measures ranked box detections; it is not 92.6% accuracy, push-event recall, or new-room performance. Later, V4 scored .883 rat AP50 on 439 reviewed new-room frames, below the .90 target, and missed a parked plush in recorded replay. V5 used those clips for tuning. Its [fresh box test](../vision/V5_FRESH_RESULTS.md) did not establish the .90 target, and its [fixed event test](../vision/V5_FORMAL_EVENT_RESULTS.md) failed the false-alert limit. This dated video does not show those later results.

The earlier [V2 clip](out/barn-owl-training-demo-v2.mp4) documents V3, which scored .943 on reused validation clips and failed its separate one-time independent test at .870 combined rat AP50 (.844 on the fresh new-angle positive clip). [V1](out/barn-owl-training-demo-v1.mp4) predates that test and has a stale “independent scene test pending” caption. Use the [V5 recorded-development montage](v5-montage.md) for the current detector snapshot; keep this video for V4 training history.

Inputs and SHA-256:

| Artifact | SHA-256 |
| --- | --- |
| `vision/runs/modal-rat-v4-20260926/results.csv` | `291002f3703986abe92ed686d4ca6ec0ab868f6cecb61bb62d9ecbf6feb6a3d4` |
| `vision/runs/modal-rat-v4-20260926/rat.onnx` | `fb557bd9c1dafa7466a45afb50ac47668550a666a44f1791af714011a0bf1b27` |
| `vision/clips/zoom15_b.mp4` | `d498ea78b27621d406fe2d64b3e8852477fb8229151fa21ceb674931f2124529` |
| `pitch/out/barn-owl-training-demo-v3.mp4` | `32b820475cd5768ddb573ad7c13d85a29d795d1246cb5fc7cb9be794b3705d1c` |

The source is `pitch/make_training_video.py`. Run `vision/.venv/bin/python pitch/make_training_video.py --version v3` with `ffmpeg` on `PATH`. Historical V1 and V2 can still be regenerated with their version flags. The V4 metrics come from `vision/runs/modal-rat-v4-20260926/weak_test_once/verification/verification_report.json`; model selection and capture limits are recorded in `candidate_lock.json`.
