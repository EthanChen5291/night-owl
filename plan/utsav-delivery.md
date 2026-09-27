# Utsav delivery status

The [technical report for Bruno and Devpost](../docs/utsav-technical-handoff.md) is the short account of what Utsav built, how the detector was trained, what the tests show, and what remains. This page records the handoff boundaries for the Night Owl demo.

## Delivered

- The [web app](../web/README.md) displays Sanjavan's city risk exports, H3 cells, proposed sensor sites, inspection backtests, and sightings. It has a usable map when the optional 3D city tiles are absent. Model exports and fixtures are labeled separately.
- The [API](../api/README.md) owns event persistence, per-cell and per-month posterior updates, and re-ranking of existing site candidates. It preserves the actual source month and ignores duplicate deliveries for scoring. The web app refreshes from the API after events. The optional assistant reads the same live month and plan budget.
- The [YOLO11n detector](../vision/V5_RESULTS.md) targets the team's plush prop in room light and suppresses people. Reviewed whole-clip data, training settings, checkpoint selection, PyTorch/ONNX parity checks, replay audits, and sealed evidence archives are linked from the [artifact index](../vision/artifacts/README.md).
- A [live Pi rehearsal](../vision/V5_LIVE_RESULTS.md) delivered one reviewed plush event to an isolated local API. The map showed its crop and moved the demo cell from score 0.1297 to 0.1618 and plan rank 2 to 1. The indoor camera used an assigned demo H3. This is one integration check, not a field-accuracy result.

Sanjavan owns the city models. Model A predicts complaints; Model B estimates active rat signs conditional on proactive inspection. Utsav's vision detector answers a different question: whether the camera sees the plush prop. A sensor event updates the API posterior; it does not retrain the city models.

## Detector decision

**V5 stays a limited, centered, room-lit plush demo candidate. V6 was rejected. Neither is promoted to the Pi's production model.**

| Evidence | Result | Decision |
| --- | --- | --- |
| V5 fresh box test, 369 held-out frames | As-run rat AP50 0.616. A later source-only audit found flawed reference boxes; no corrected score was adopted. | The 0.90 target is unestablished. |
| V5 fixed event test, two new whole recordings | 18 of 19 plush appearances alerted. The 190.409-second no-plush video produced 17 false alerts, mostly on a cap. | Failed the false-alert gate; [all 60 event crops were reviewed](../vision/V5_FORMAL_EVENT_RESULTS.md). |
| V6 development validation after adding 42 reviewed no-plush frames | Table-floor rat AP50 0.891727 below its 0.935526 floor; table-floor person 0.800513 below 0.819889; old-clip combined person 0.741646 below 0.807739. | Rejected at preset floors. |
| [V6 warmup comparison](../vision/V6_WARMUP_RESULTS.md), changing only `warmup_bias_lr` from 0.1 to 0 | Table-floor rat rose to 0.915 but still missed its floor. Table-floor person rose to 0.837729 and passed; old-clip combined person rose to 0.797100 but still missed. | PyTorch/ONNX parity passed, but the guards still failed. No formal replay or Pi promotion. |

The V5 formal source clips were used to build V6's hard negatives. They are development material for V6 and cannot supply an independent V6 test. The [V5 fresh report](../vision/V5_FRESH_RESULTS.md) and [formal report](../vision/V5_FORMAL_EVENT_RESULTS.md) retain the failed results. The [live rehearsal](../vision/V5_LIVE_RESULTS.md) confirms wiring only.

## Run and verify

From the repository root, start `./api/run.sh`, then run `pnpm --dir web install --frozen-lockfile` and `pnpm --dir web dev` in a second terminal. Open `http://localhost:5173`. Run `uv run --project api pytest -q api/tests`, `pnpm --dir web build`, and `pnpm --dir web lint` before a handoff. The [artifact index](../vision/artifacts/README.md) gives the candidate and evidence archive hashes and verification instructions.

`api/fake_event.sh`, `api/fake_sightings.py`, and `api/real_sightings.py` are staged rehearsal inputs. The last script uses animal photos but assigns artificial node, time, and cell fields. Use these only against an isolated local API, and identify them as fixtures. The verified live Pi event is documented separately.

## Remaining work

Collect new whole-session footage with plush appearances and no-plush activity, freeze source-only truth before running the detector, and audit every alert against its original frame. Fix the cap and shoe confusion on development data. A new independent test at fixed settings must pass both box and event gates before a deployment claim. Outdoor rats and infrared operation remain untested.
