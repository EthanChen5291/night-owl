# V5 fresh recorded-video test

**The 0.90 target is not established.** The first fixed test completed at 2026-09-27 04:01:46 UTC. Its preserved as-run combined rat AP50 was **0.615779**. Post-run source-only review of all 193 positive sampled frames found shifted and oversized reference boxes, so that number has an annotation-quality caveat. Frozen labels, model settings, and the original report remain unchanged; no corrected-label score has been calculated.

The runtime test exposes a separate, real problem: the plush's second coarse presence began near 47.352 seconds, but its first alert came at 106.242 seconds, a **58.890-second delay**. The early portion was largely at the image edge. The model is a supervised room-lit demo candidate; it is not a validated 90% detector.

## Fixed candidate and untouched inputs

- V5 lock: 2026-09-27 03:04:44.203198 UTC. ONNX SHA256 `652a05e8c08aaee11a2b4d3c9ae4c737387bf8ffcac3372a4d83d0df7d80ed3d`; lock SHA256 `22ffcee2d241eb0c016d0a3ae5d178ef8d35e1f6541d1b20674f2c9a81237259`.
- Frozen source labels and intervals preceded all test predictions. The two source clips were excluded from training and checkpoint selection. Source/eval image-label fingerprints and clip hashes matched after the run.
- Grayscale 416, confidence 0.70, NMS 0.45, three hits within one second, two-second cooldown, and the locked person/size filters stayed fixed. Every decoded video frame was processed. No live worker or API POST was used.
- 369 reviewed sampled frames, two excluded positive frames, 165 rat boxes, 207 person boxes. Sampled ground truth does not certify every intervening video frame.

## As-run box results

| Source | Reviewed frames | Rat AP50 | Person AP50 |
| --- | ---: | ---: | ---: |
| Plush and people, `fresh_032300` | 193 | 0.703102 | 0.508685 |
| People/objects, `fresh_031823` | 176 | No rat GT | 0.487875 |
| Combined | 369 | **0.615779** | **0.492688** |

PT and ONNX AP values matched exactly. These are the original machine results, not a corrected-label score. Review subsequently confirmed that rat reference boxes in sampled frames 149–153 and 157–162 sit too low. The second source-only review also flagged box extents at the right edge (101–106) and under the table (133–138 and 180–187), plus visibility ambiguity in frames 48 and 100. Thirty-one source-estimated box proposals are preserved separately as drafts, not approved replacement ground truth. Person boxes were not reannotated. Root directly checked raw frame 149 and representative native comparison panels. The model still has a real edge-detection limitation; the AP annotation error must not be confused with export failure or hidden by editing the frozen test.

## Recorded event behavior

| Source | Frames processed | Emitted events | Source/crop audit |
| --- | ---: | ---: | --- |
| `fresh_032300`, 195.144693 seconds | 2,926 | 34 | All 34 crops target the visible plush; zero other-object crops |
| `fresh_031823`, 175.937013 seconds | 2,638 | 0 | Zero events; sampled source review found no plush |

The positive events comprise 15 firings during the first presence, 11 during the second, and eight during a final end-censored appearance. The two completed presences each eventually produced an alert. These are **two coarse presence episodes, not 34 independent pushes**. The final parked segment produced four repeat alerts. An independent reviewer inspected all 34 event crops beside exact native source frames; root spot-checked the initial match, delayed second match, and parked detections.

The no-plush video is 4.062987 seconds short of 180 seconds. Its zero-event result is useful but does not meet the specified three-minute negative coverage. The two completed presences do not meet the specified 20-push coverage. The formal event gate remains incomplete, and the box gate was not established.

## Delivery and next check

The immutable [V5 development candidate](artifacts/rat-litroom-v5-development-candidate-20260927.zip) retains SHA256 `5d4098dfea86dc80de230f9a689dad4ccdf819c194ac2ba5cdf96185bd5ca38e`. The separate fresh-test supplement has a [core ZIP](artifacts/rat-litroom-v5-fresh-test-evidence-20260927.zip), SHA256 `d81d8b66672809943e483fccc03f729d43e38937d63d162c99bd3f1e67da35f3`, and [source-review ZIP](artifacts/rat-litroom-v5-fresh-test-evidence-20260927-source-review.zip), SHA256 `122a5be2d353d4afc9708b9d751b6ef125a466d901db39dcd76c8592e12d9ba7`. They preserve originals, frozen labels, the failed as-run score, replay evidence, review notes, and the unadopted annotation proposals. Extract both into one parent folder and run the included `verify_bundle.py`; the clean extraction verified all 2,395 listed files. See the [artifact index](artifacts/README.md) for sizes and instructions.

For the hackathon, keep the plush fully visible in a supervised lit scene and show the result as a prototype. Positive live Pi-to-local-API/map integration still needs verification. IR, live wild rats, different sites, and general 90% performance remain unverified. Any future training or selection using these test clips consumes them as development data and needs a new reserved test.

## Later separate event test

The subsequent fixed test on two new whole clips detected 18 of 19 source appearances but emitted 17 false alerts in 190.409 seconds. It failed the formal event requirements. This does not change the first box-test report above. See [the separate event result and audit](V5_FORMAL_EVENT_RESULTS.md).
