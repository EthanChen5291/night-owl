# V6 result: rejected development candidate

V6 trained for 30 epochs and exported an ONNX detector, but it **failed the predeclared regression guards**. It did not replace `pi/rat.onnx`, and no V6 full-video replay or Pi switch followed. The ONNX SHA256 is `39b44c2b26988479e06a2a1ccf4e3b9c85f81cd3091dc879976ca931d71a7e5d`.

| Tuned validation group | Rat AP50 | Rat floor | Person AP50 | Person floor |
| --- | ---: | ---: | ---: | ---: |
| Metal `zoom15_b` | 0.9950 | 0.9597 | undefined | undefined |
| Floor `table_c` | **0.8917** | 0.9355 | **0.8005** | 0.8199 |
| Moving `new_room_014327` | 0.9650 | 0.9308 | 0.7632 | 0.7541 |
| Old combined (`zoom15_b` + `table_c`) | 0.9685 | 0.9519 | **0.7416** | 0.8077 |

Across all 146 repeatedly used validation frames, PT and ONNX matched exactly at square 416: rat AP50 0.964575 and person AP50 0.739308. Raw-output parity also passed. The overall rat score clears 0.90, but floor rat, floor person, and old-combined person scores miss their guards. These clips guided V5 and V6 decisions, so none is a fresh test of V6.

The frozen dataset has 694 train frames and 146 unchanged V5 validation frames. It adds 42 visually reviewed no-plush frames from the V5 formal negative recording: 17 person boxes and 25 empty labels. Codex agents reviewed all 67 selected native candidates; an independent root review of overlays found four missing person boxes and eight ambiguous human-boundary frames, which were corrected or excluded before training. The earlier 50-frame draft remains separately preserved. These are agent-reviewed labels without human signoff. The formal negative is now **consumed development data**, not an independent V6 test. The formal positive did not enter V6 training.

The first Modal launch failed while importing `modal_train_v6.py` (`Path(__file__).resolve().parents[2]` was invalid in the container); it completed zero training epochs. The failed launcher, log, and release remain intact. Root authorized one infrastructure recovery using the same frozen data, starting weights, and recipe. That job completed 30 epochs and selected Ultralytics trainer `best.pt` only on the old whole-clip validation split. Its output, both launcher sources, preflight receipts, and failed-import log are preserved in the [rejected-candidate evidence bundle](artifacts/README.md). The local working copies remain under `vision/runs/modal-rat-v6-20260927/`.

Post-run learning-rate check: the resolved V6 configuration used `lr0=5e-5`, `warmup_bias_lr=0.1`, and three warmup epochs. Ultralytics 8.4.163 applies that warmup to the bias parameter group; `results.csv` logs its rate at 0.0670663, 0.0337485, and 0.000429663 in epochs 1–3, versus 0.0000164751 for the other groups in epoch 1. V5 also used `warmup_bias_lr=0.1` with a three-epoch warmup. These are learning rates, not measured weight changes. The warmup mismatch is verified; its contribution to the V6 regression is unproven. The frozen configuration and result were not changed.

Frozen manifest SHA256: `4c93e15d309b1cd4fd8758bf1938642d7f37a95b0023bee18253a0b110bfe515`. Dataset image/label fingerprint: `9346b7f24af41366c3f75cc97339ef22cc8aaecec678edc6134c5fffa5f10335`. Original formal negative MP4 SHA256: `30c7f71326910f5b182e7af73ae03eb6e43f260ac2c1501814a074c6c7bcc3ec`. The original formal videos remain in the immutable V5 formal evidence archive.

The V5 formal negative produced 17 false events; V6 did not reach the planned replay check. V5 remains the existing development model with its documented formal failure. Neither model has passed a new, independent 0.90 scene test, so no broad detection claim follows from these results.
