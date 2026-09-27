# V5 plush-detector development result

**Status: locked candidate; fresh independent test pending.** V5 was trained after V4 missed a parked plush and fired once on a dark case in newly recorded room footage. All three V4 new-room test clips were deliberately consumed as V5 **development** data. V5 results on them measure adaptation, not generalization. The V4 candidate and its new-room failure supplement remain unchanged.

## Fixed run and selection

The reviewed V5 dataset froze at 2026-09-27 02:43:44 UTC: 652 train frames, including 572 unchanged V4 train frames, 20 sampled parked/transition frames, and 60 sampled people/empty frames. The 146 development validation frames comprise the unchanged whole metal `zoom15_b` and floor `table_c` clips (49 frames) plus the whole moving new-room `014327` clip (97 frames). Train and validation clips do not overlap. Manifest SHA256 `d9a872f4b7e0a479e3983701c6d0751f692619d677b1ec7bf7eeb72240b7edcf`; full image/label fingerprint `78cd5d4fd8fd15453f67e3e5f8a7c7a6e9b9b271fcb4b511223897442287ed15`. Original V4 image/label pairs and moving-clip test pairs were byte-checked before the run.

One Modal L4 trained grayscale YOLO11n at 416 px for 60 epochs, batch 8, AdamW initial learning rate 0.0001, mosaic 0, scale 0.2, translate 0.05, and brightness variation 0.15. It started from exact V4 selected PT SHA256 `7f607ddf866c991b3f74694f7901f24df0e9fc7353e8960041ac7d7154af1ecc`; the launcher checked that hash locally and remotely. A one-hour timeout and zero retries bounded the run. Full resolved Ultralytics arguments, dataset and launcher hashes, logs, curves, and every five-epoch checkpoint score are in the run/bundle. Root approved the preregistered recipe before launch.

Fourteen saved checkpoints were scored once on square-416 CPU development AP (confidence 0.001, NMS IoU 0.7). Ten met all predeclared floors. Epoch 35 maximized the minimum rat AP50 across the three whole clips and was selected before any V5 replay. Exported ONNX passed the same per-domain floors and PT/ONNX raw-output and AP parity. The lock was written at 2026-09-27 03:04:44 UTC, before V5 full-video replay: `candidate_lock.json` SHA256 `22ffcee2d241eb0c016d0a3ae5d178ef8d35e1f6541d1b20674f2c9a81237259`. Selected PT SHA256 `0906a038d9795e1606d6890627fefe4e4d5eaa4efdadbdb8cab11aaf304b4aa9`; ONNX SHA256 `652a05e8c08aaee11a2b4d3c9ae4c737387bf8ffcac3372a4d83d0df7d80ed3d`.

| Development validation set | Rat AP50 | Person AP50 |
| --- | ---: | ---: |
| Metal `zoom15_b`, whole clip | 0.989737 | No person GT |
| Floor `table_c`, whole clip | 0.965526 | 0.869889 |
| Moving new-room `014327`, whole clip | 0.960806 | 0.804068 |
| Two old clips combined | 0.981870 | 0.857739 |
| All 146 sampled frames | **0.975279** | **0.798870** |

These are Modal square-416 CPU PT and ONNX values, which matched exactly. An independent Mac CPU run with Ultralytics 8.4.163 also had exact PT/ONNX parity but slightly different AP: combined rat 0.975630/person 0.794578; moving rat 0.962097, floor 0.971471, metal 0.989737. Its fixed-confidence 0.70 Pi parser matched 22/31 moving, 9/12 floor, and 16/17 metal rat boxes at sampled times. An earlier local verifier accidentally used its default confidence 0.50 for parser counts; its AP was unaffected, the report is retained, and `verification_addendum.md` records the corrected 0.70 check. No threshold or checkpoint changed because of it.

## Locked full-video development replay

The V5 lock reused V4's confidence 0.70, NMS 0.45, grayscale 416, person suppression, floor_y 0, rat width 0.01–0.65, three hits in one second, and two-second cooldown. Five complete original videos were replayed once with no API POST. Independent reviewers inspected emitted crops beside native source frames.

| Clip | Decoded frames | Events | Crop audit |
| --- | ---: | ---: | --- |
| Moving new-room `014327` | 1,454 | 14 | 14 plush, 0 false; all four source-observed appearances, including before the last occlusion |
| Parked new-room `014605` | 2,429 | 64 | 64 plush, 0 false; none after removal; one continuous exposure, not 64 pushes |
| Source-reviewed people-only `020101` | 2,718 | 0 | 181.206 seconds with no emitted event; source review sampled several time grids |
| Old metal `zoom15_b` | 3,112 | 64 | 64 plush, 0 false; every V4 event time covered within 1.000 second |
| Old floor `table_c` | 3,947 | 44 | 44 plush, 0 false; every V4 event time covered within 1.067 seconds |

The moving clip's V4 dark-case false event at 0.267 seconds disappeared. V5's first event was plush at 12.472 seconds, after the source-observed onset around 12 seconds. The parked clip had zero V4 events at the same confidence and now fires from 0.133 seconds. These are development regressions on footage used to build/select V5, and repeated events do not establish one-to-one push recall. The people-only clip was used in V5 training, so its zero-event result is not an independent negative-reel gate.

A saved-frame smoke test on Raspberry Pi ARM64 with ONNX Runtime 1.22.1 gave one plush proposal at confidence 0.931 and no proposal on one negative saved frame, with median inference about 60 ms. It did not test positive live-camera event accuracy. Formal 20-push recall, a separate untouched three-minute negative test, live-rat/infrared behavior, and fresh-room generalization remain unverified. The candidate is not promoted to `pi/rat.onnx`.

See the candidate bundle README for artifact contents and exact hashes. Full source MP4s remain in the immutable V4 model and new-room evaluation archives, identified by SHA256 in each replay report. A genuinely fresh post-V5 recording must be reserved and visually labeled before any V5 prediction to test improvement without selection leakage.
