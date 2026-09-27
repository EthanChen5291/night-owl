# V6 bias-warmup comparison: rejected

This one-run development comparison changed only `warmup_bias_lr` from 0.1 to 0.0. The frozen 694-train/146-validation dataset, V5 starting checkpoint, 30 epochs, seed, pinned software, other training arguments, checkpoint-selection rule, and AP50 guard floors matched the original V6 run. The [original V6 result](V6_RESULTS.md) remains unchanged.

| Tuned validation group | Original V6 rat | Warmup rat | Rat floor | Original V6 person | Warmup person | Person floor |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Metal `zoom15_b` | 0.9950 | 0.9922 | 0.9597 | undefined | undefined | undefined |
| Floor `table_c` | 0.8917 | **0.9150** | 0.9355 | 0.8005 | 0.8377 | 0.8199 |
| Moving `new_room_014327` | 0.9650 | 0.9650 | 0.9308 | 0.7632 | 0.7866 | 0.7541 |
| Old combined | 0.9685 | 0.9640 | 0.9519 | 0.7416 | **0.7971** | 0.8077 |

Across all 146 tuned validation frames, square-416 ONNX rat AP50 changed from 0.964575 to 0.964153 and person AP50 from 0.739308 to 0.776193. PyTorch/ONNX parity passed. Floor rat and old-combined person still miss their predeclared guards, so the comparison model is rejected. No formal replay, Pi switch, retry, or promotion followed.

The comparison audit at `vision/runs/modal-rat-v6-warmup-20260927/COMPARISON_REPORT.json`, SHA256 `881959ae93d0b4fd1800881357dfa26e44ac0663df5ce39233b8af4fc29a17f8`, is prepared for the separate evidence archive. It verifies that resolved training arguments differ only in bias warmup and run-specific paths. The frozen dataset manifest SHA256 is `4c93e15d309b1cd4fd8758bf1938642d7f37a95b0023bee18253a0b110bfe515`; its image/label fingerprint is `9346b7f24af41366c3f75cc97339ef22cc8aaecec678edc6134c5fffa5f10335`. The warmup launcher SHA256 is `ee45a7446dc75427307b3d952af5e3bad07c446c425663347f518571aa7a6d56`.

The higher person and floor-rat scores are consistent with warmup affecting this run, but one seed cannot establish that warmup caused the original V6 failure. All scores come from clips already used for model decisions, so they do not establish fresh-scene performance.

The [comparison archive](artifacts/rat-litroom-v6-warmup-comparison-20260927.zip) contains the weights, resolved settings, logs, and audit. SHA256: `412034c6e1f870e735b3d6787eb40d70136ef66b6bded0fc127afc42f9e4b09d`, 28,907,334 bytes. Root checked its CRC and all 26 file hashes. It references the original V6 archives for the unchanged dataset.
