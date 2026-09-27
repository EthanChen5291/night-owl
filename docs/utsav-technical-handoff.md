# Utsav's technical report for Night Owl

## Devpost-ready summary

I built the link between Night Owl's city risk map and a Raspberry Pi camera detector. The web app shows Sanjavan's block-level risk estimates, candidate sensor sites, inspection backtests, and incoming sightings. I made the API responsible for updating a cell's probability and re-ranking existing sites after an accepted detection, so the map and assistant read the same result. For the camera, I trained a two-class YOLO11n model on reviewed footage of our plush rat and people, exported it to ONNX, and tested both box detections and full-video alerts. One live Pi sighting reached a local API and visibly changed the map. The detector remains a **room-lit plush demo candidate**: a fresh recorded event test found 17 false alerts in 190 seconds without the plush, and a follow-up V6 run failed its preset validation floors.

## What I built

Night Owl combines [Sanjavan's two city models](../model/README.md) with a separate vision detector. The city models estimate where 311 complaints are likely and where inspected lots show active rat signs. The second outcome is conditional on inspection; it is not a rat count. My vision model looks for the team's plush prop in camera frames. Its scores do not validate the city models or measure detection of wild rats.

I completed the [React and three.js map](../web/src/App.tsx) so it can display H3 cells, inspection backtests, proposed sensor sites, and sighting crops. The map remains usable without the optional 3D city tiles. The [API](../api/README.md) persists events and maintains a Beta-Binomial estimate per cell and month. Accepted rat events update the served cell's probability. They can re-rank existing tree-backed site candidates; the server does not invent new pin locations. Duplicate, person, and below-threshold events do not change that estimate. The API reports the actual month and whether it served a model export or a fixture, even when a requested month is unavailable. The web app refetches cells and plans after events, and the assistant uses that same live API state.

The [Pi detector](../vision/pi/README.md) runs a grayscale YOLO11n model and emits an alert after three qualifying hits within one second, with a two-second cooldown and person suppression. The runtime confidence was fixed at 0.70 for the V5 tests below. Saved-video replay uses the same event rules and does not post to the API.

## How I trained and checked the detector

Codex-assisted reviewers boxed visible plush bodies and people in frames from whole source clips. They recorded genuinely empty frames and excluded ambiguous views; the labels did not receive independent human signoff. The V4 dataset contained 572 reviewed training frames, including hard negatives such as chair fabric. V5 started from the selected V4 checkpoint and used 652 training frames with 146 development validation frames. The three new-room recordings that exposed V4 failures became V5 development data, so their V5 performance cannot count as a fresh test. The team trained with repeated-channel grayscale at 416 pixels on a bounded Modal L4 run, selected a checkpoint on whole development clips, then checked PyTorch and ONNX with the same square-416 evaluation. [Training method](../vision/V5_RESULTS.md) · [dataset and trial history](../vision/TRAINING_RESULTS.md)

We froze new whole recordings before each independent V5 check. Reviewers compared every emitted alert crop with its original video frame. Box AP50 measures localization across confidence thresholds; it does not measure whether the Pi sends a timely, correct alert. Repeated alerts on one plush exposure also do not count as separate pushes.

| Check | Result | What it means |
| --- | --- | --- |
| V4, 59 reserved frames from the same camera and table session | Rat AP50 0.926 | Passed that narrow box check; changed-room rat AP50 later fell to 0.883 on 439 frames. |
| V5, 146 development frames | Rat AP50 0.975; person AP50 0.799 | Useful for checkpoint selection, not a fresh generalization result. |
| V5, 369 fresh whole-clip frames | As-run rat AP50 0.616; person AP50 0.493 | PyTorch and ONNX matched. A later source audit found flawed plush reference boxes. No corrected labels or score were adopted, so a 0.90 claim is unestablished. |
| V5, separate fixed-rule event test | Alerts for 18 of 19 reviewed plush appearances; 17 false alerts in 190.409 seconds without plush | Failed the false-alert gate of fewer than 0.5 per minute. Sixteen alerts targeted a cap and one a shoe. Nineteen appearances also fell short of the requested 20-push coverage. |
| V6, preset development regression checks | Table-floor rat AP50 0.892 vs 0.936 floor; table-floor person 0.801 vs 0.820; old-clip combined person 0.742 vs 0.808 | Rejected. V6 received no formal replay or Pi promotion. |

The [V5 fresh box report](../vision/V5_FRESH_RESULTS.md) preserves its original as-run score and label audit. The [formal event report](../vision/V5_FORMAL_EVENT_RESULTS.md) preserves the frozen source intervals and review of all 60 emitted crops. V6 added 42 reviewed no-plush frames from the failed V5 negative recording to training while keeping the 146-frame development validation split unchanged. Its result is a development check on a consumed scene, not new independent evidence.

The [V6 report](../vision/V6_RESULTS.md) records that configured `lr0=0.00005` still inherited `warmup_bias_lr=0.1`, as V5 did, and epoch-one bias learning rate reached 0.0670663; this is a possible contributor, not a proven cause. The rejected V6 run leaves V5 as the limited centered, room-lit plush demo candidate. It does not repair V5's failed formal event test.

## Live integration and limits

In a bounded live Pi observation, V5 processed 1,346 camera frames over 89.859 seconds and saved six alerts from one visible plush exposure. All six crops showed the plush. We relayed **one** unchanged event through a Pi-loopback SSH forward to an isolated local API; it returned `accepted: true` and did not repost on a second scan. The cell moved from one to two sightings, its Model B score from 0.1297 to 0.1618, and its plan rank from 2 to 1. The frontend displayed the crop. The indoor rehearsal used an assigned demo H3, so that map cell does not establish the camera's physical location. The worker and tunnel stopped afterward; the production camera service was unchanged. [Live result and screenshots](../vision/V5_LIVE_RESULTS.md)

This proves one plush-to-local-map path. It does not establish a reliable false-alert rate, push recall, outdoor performance, infrared performance, or wild-rat detection. The V5 formal failure and V6 rejection still govern deployment.

## Reproduce and hand off

From the repository root, start the API and web app in separate terminals:

```sh
./api/run.sh
pnpm --dir web install --frozen-lockfile
pnpm --dir web dev
```

Run `uv run --project api pytest -q api/tests`, `pnpm --dir web build`, and `pnpm --dir web lint` for software checks. The [artifact index](../vision/artifacts/README.md) links the sealed V4 and V5 candidates, fresh-test evidence, formal event evidence, and live integration evidence with SHA256 and extraction checks. The [V5 candidate ZIP](../vision/artifacts/rat-litroom-v5-development-candidate-20260927.zip) predates its fresh failures; it is not a production release.

Before any broader detector claim, collect new whole-session plush and no-plush recordings, freeze source-only truth before inference, and audit alerts on their original frames. Improve the cap and shoe confusion using development data, then require a new independent test at fixed settings. Keep the city-model evaluation separate from the camera detector's evaluation.
