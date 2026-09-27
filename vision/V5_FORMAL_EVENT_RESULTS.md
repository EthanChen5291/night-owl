# V5 fixed event test

**The formal event test failed.** V5 detected 18 of 19 source-reviewed plush appearances, but emitted 17 false alerts during the separate 190.409-second no-plush recording. All 60 emitted crops were independently reviewed against exact source frames. The model, confidence threshold, event rules, and source intervals stayed fixed.

| Measurement | Result |
| --- | ---: |
| Complete source appearances | 19 |
| Appearances with a verified plush alert | 18 (94.7% observed recall) |
| Positive-clip emitted events | 43, all plush; 25 repeat firings |
| Negative-clip false events | 17 |
| Negative duration | 190.409467 seconds |
| False events per minute | 5.356877 |
| Required negative rate | Less than 0.5 per minute |

The source review found 19 distinct appearances despite the operator's description of 20 passes. It retained the short hand-held first appearance, which the model missed. Every other appearance produced a verified plush alert. All conservative gaps between appearances exceeded 3.7 seconds; no easiest-20 subset was selected. Nineteen appearances are also short of the specified 20-push coverage.

Sixteen false alerts target one baseball cap: fifteen while it is stationary and one after it moves. The last false alert targets a partial shoe at the frame edge. They are repeated events on two distractor types, not 17 different objects. Raising the threshold or changing an image region after seeing this result would be development tuning, not a new test pass.

## Frozen inputs and audit

- Locked V5 ONNX SHA256: `652a05e8c08aaee11a2b4d3c9ae4c737387bf8ffcac3372a4d83d0df7d80ed3d`. Confidence 0.70, grayscale 416, NMS 0.45, three hits within one second, two-second cooldown, unchanged person and size filters.
- Positive original: `formal_040512.mp4`, 4,319 frames, 288.048507 seconds, SHA256 `701e40f5c24691acdd602152ea0208dd9fa25c3ec57f6b0616c9118a969b623a`.
- Negative original: `formal_041054.mp4`, 2,855 frames, 190.409467 seconds, SHA256 `30c7f71326910f5b182e7af73ae03eb6e43f260ac2c1501814a074c6c7bcc3ec`.
- Frozen source truth SHA256: `754fa86b0dc8ed02ea3fd533454fcf0a4c07101fc5337afac6421290b312891b`. The separate root release pins source, truth, model, and all four inference/runner implementation files before the one replay.
- Every original video frame was processed. Source-only presence review used sampled frames plus denser boundary checks and actual presentation timestamps. All emitted source frames and crops were then inspected. Root checked representative positive, cap, and shoe evidence. No API POST occurred in this recorded test.

The raw report retains its original pending-audit status. A separate `audited_result.json` and `ROOT_ADJUDICATION.md` record the completed visual review and failed gate. The [evidence ZIP](artifacts/rat-litroom-v5-formal-event-evidence-20260927.zip) contains both originals, frozen truth, exact code, logs, all event crops, audit records, and a checksum verifier. See the [artifact index](artifacts/README.md) for the archive hash.

## What follows

This is an event test, not box AP50 or a citywide accuracy estimate. It does not repair the annotation defects in the [earlier fresh box test](V5_FRESH_RESULTS.md), and the 0.90 box target remains unestablished. Any reuse of these failed clips for V6 training or development consumes them as development evidence; new independent footage is required for a later generalization claim. The original V5 result and model bundle remain unchanged.
