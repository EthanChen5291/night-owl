# Night Owl: model and detector branch

Night Owl is a DivHacks prototype for comparing NYC rat complaints with active rat signs found during inspections. This `utsav/model` branch holds the cell models and exports, detector experiments, Pi evidence, and pitch. The [frontend branch](https://github.com/EthanChen5291/poc/tree/utsav/frontend) has the current web and API integration. The `web/` and `api/` directories in this checkout may lag that branch, so use its README to run the latest map.

## What the model measures

Model A predicts complaints. Model B estimates active-sign risk from building and environmental features without complaint counts. The Silence Score is the gap between their percentile ranks. These are planning signals, not rat counts or measured prevalence in unswept cells. See [model decisions and pipeline](model/README.md) and the exported [cell scores](model/out/cells.json).

The [119-month backtest](model/out/backtest.json) ranks the top 50 **among cells swept each month**. Model B's picks averaged active signs on 19.5% of inspected lots, versus 15.2% when ranking by prior 311 complaints. That 4.3-point gap applies to the swept sample; it does not show what crews would find in other cells or what a deployment would cause. The planner and other outputs are under [`model/out/`](model/out/).

## Detector and live prototype

The V5 room-lit plush detector remains the demo candidate. During one 89.859-second live Pi camera observation, it processed 1,346 frames and saved six crops that reviewers confirmed showed the plush. The team relayed **one** event to an isolated local API, which accepted it. The map showed a second sighting, and that demo site's served score moved .1297→.1618 and plan rank 2→1. This proves one camera-to-map path worked; it is not a repeated-detection or field-performance result. Read the [live result](vision/V5_LIVE_RESULTS.md) and [evidence archive](vision/artifacts/README.md).

Detector readiness is separate. V5's fixed recorded event test alerted on 18 of 19 reviewed plush appearances but fired 17 false alerts on a cap and shoe during 190.409 seconds without plush. It failed the false-alert gate. Its fresh box test scored .6158 rat AP50 as run, with documented reference-label defects and no corrected score; the .90 box target was not established. V6 trained on added hard negatives but failed preset development checks and was not replayed or put on the Pi. A [controlled warmup correction](vision/V6_WARMUP_RESULTS.md) improved floor-scene rat AP50 to 0.915, but still missed two fixed guards. No IR, wild-rat, or field claim follows from these runs. See [V5 formal event results](vision/V5_FORMAL_EVENT_RESULTS.md), [V5 fresh box results](vision/V5_FRESH_RESULTS.md), and [V6 results](vision/V6_RESULTS.md).

## Where to start

| Need | File |
| --- | --- |
| Model methods, exports, and limits | [model/README.md](model/README.md) |
| Detector runs and Pi code | [vision/RUNBOOK.md](vision/RUNBOOK.md) and [vision/pi/README.md](vision/pi/README.md) |
| Verifiable model and video bundles | [vision/artifacts/README.md](vision/artifacts/README.md) |
| Three-minute Night Owl deck and script | [pitch/README.md](pitch/README.md) and [V20 PPTX](pitch/out/night-owl-three-minute-pitch-v20.pptx) |
| Current web/API app | [frontend branch README](https://github.com/EthanChen5291/poc/blob/utsav/frontend/README.md) |
| Original project plan and data contract | [plan/master-plan.md](plan/master-plan.md) |

The plan records earlier intentions; the linked result files record what the team built and tested. Historical Barn Owl filenames remain in earlier decks, evidence bundles, and some app paths.
