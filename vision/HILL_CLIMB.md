# Rat detector recipe trials

This log keeps every bounded Modal recipe trial against the frozen v2 reviewed dataset. The image/label fingerprint is `52d386b7d67e930e8929f62464664220723beac888f90b982934c3be7a063d04`; the manifest SHA256 is `ae62db7c06a99e289fa878ab1b6d9804da320b42dd8c4cd1ea2cb1759cbf764c`. Training uses 252 frames. Validation keeps the entire reflective-metal-table `zoom15_b` and pink-floor `table_c` clips out of training (49 frames). The model remains YOLO11n with two classes, grayscale input, and a static square 416-pixel ONNX export.

Compare runs using the same validation call: 416 pixels, batch 1, `rect=False`, `conf=0.001`, `iou=0.7`, `max_det=300`. Report rat and person AP50 overall and rat AP50 for each whole clip. Repeated use of these holdouts for checkpoint and recipe selection makes the results tuned validation evidence. Separate reserved clips are needed for a final independent estimate. Formal promotion also requires the event-level push and negative-reel gate.

| Run | Recipe difference | Checkpoint selection | Overall rat AP50 | `zoom15_b` rat AP50 | `table_c` rat AP50 | Outcome |
|---|---|---|---:|---:|---:|---|
| `modal-rat-v2-20260926` | AdamW lr0 .0003, batch 8, 150 epochs, mosaic 0, scale .15, translate .05, hsv_v .15 | Ultralytics best by combined mAP50-95 | .7903 | .9367 | .6511 | ONNX parity passed; rat box gate failed |
| `modal-rat-v3-lr1e3` | AdamW lr0 .001, batch 8, 92 of 100 epochs, patience 35; other augmentations unchanged | Every 5 epochs plus trainer best/last, select highest square-416 rat AP50 (trainer best won) | .8087 | .9055 | .7701 | ONNX/PT CPU AP parity passed; rat box gate failed |
| `modal-rat-v3-aug` | AdamW lr0 .0005, batch 8, 43 of 100 epochs, patience 35, mosaic .3, scale .35, translate .1, hsv_v .25 | Highest square-416 rat AP50 among 11 saves: last.pt | .8659 | .9504 | .7038 | PT/ONNX CPU AP parity passed; person AP50 regressed to .4963 |
| `modal-rat-v3-aug/trainer_best` | Same training run; checkpoint selected by Ultralytics combined fitness | Trainer best, preserved and exported separately on local CPU | .8611 | .9769 | .7622 | PT/ONNX CPU AP parity passed; person AP50 .9262; rat box gate failed |

V2's train box loss fell from 1.40 to .36, while validation box loss stayed near .86. Its best combined validation mAP50-95 occurred at epoch 16. The new trial tests faster optimization and early stopping; simply extending the v2 training curve would likely increase overfit.

Trial 1 selected from 21 saved checkpoints. Modal's GPU square-416 rat AP50 was .810984; the independent verifier ran both PT and ONNX on CPU and measured .808733. Use the independent CPU numbers in the comparison table. Metal-table AP fell by .0312 from v2 while floor AP rose by .1191. The verifier also recorded 15/17 matched metal rats and 4/12 matched floor rats at the Pi runtime confidence .5; those are frame detections, not event recall.

Trial 2's rat-only checkpoint improves the metal AP but loses person AP. Its preserved trainer-best checkpoint improves both classes over v2, but still misses the combined rat AP50 target. The trainer-best ONNX was exported locally without simplification because the local environment lacks `onnxslim`; the independent CPU verifier measured identical PT and ONNX AP50 on the fixed protocol. Trial 2 stopped at epoch 43 because Ultralytics early stopping uses combined fitness, while rat AP was still rising. The next run will use full-epoch patience and keep both rat-best and person-qualified checkpoints.
