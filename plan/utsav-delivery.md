# Utsav delivery

## Source and branch decisions

Reviewed the 18 tabs in the [team document](https://docs.google.com/document/d/1tCopxgA06s6Bap_5rZX7D0yJzjHYfhSO5ZPO8badWkI/edit?tab=t.nn7fuvesn0d5) and Ethan's available iMessage conversation through September 26, 7:25 p.m. The recent messages identify the Pi 5 plush-rat detector as the main remaining task. The first document tab assigns training, tuning, and the pitch to Utsav. The older master plan also assigns frontend integration to Utsav. New pitch examples from Ethan were checked against current exports before inclusion.

The starting remote state was fetched on September 26:

| Branch | Commit | Relationship |
| --- | --- | --- |
| `origin/main` | `3c26e60` | Current integrated application |
| `origin/ethan` | `3c26e60` | Same commit as main |
| `origin/sanjavan/model` | `19d8a5a` | Already merged into main |
| Original local `main` | `c37a84b` | 31 commits behind origin/main |

Work starts from current `origin/main` in managed worktrees. The original checkout stays intact. `utsav/frontend` owns frontend integration and pnpm tooling. `utsav/model` owns the detector, training, API feedback loop, and pitch artifacts.

## Implementation plan

1. Preserve Ethan's React/three.js map and Sanjavan's existing risk models and exported results.
2. Make the map usable without the optional city bake; complete the live data, planning, popup, and backtest interactions. Use pnpm.
3. Make the server authoritative for accepted detections, posterior updates, and subsequent candidate rankings. Preserve source months and disclose fixture data.
4. Train the existing YOLO11n detector on reviewed recordings from the actual Pi camera. Utsav confirmed that room lights are fine for the demo. Dark IR footage is excluded where the prop cannot be identified reliably. Hold out whole clips and evaluate detection events as well as boxes.
5. Require validation and ONNX parity before promoting a deployment artifact. Keep failed candidates and their results distinct from the deployable model.
6. Prepare the three-minute deck and speaker notes with current measured results and explicit limitations.
7. Review each implementation, run focused tests, then exercise the map with a real local API and a clearly identified test event.

## Scope choices

- The current detector is YOLO11n on Pi 5. The older tiny crop CNN, picamera2 loop, and ESP32 firmware descriptions are superseded.
- Model A/B training and existing backtests belong to Sanjavan and are already present. They are preserved.
- The backtest's `precision_silent` wire field actually contains Model B risk ranking among cells swept that month. Presentation labels must describe that calculation.
- New sensor evidence updates the Bayesian estimate and re-ranks existing candidate locations. This is not automatic retraining of LightGBM.
- The demo detector recognizes the plush prop. It does not establish performance on wild rats.
- Cloud services, sponsor integrations, public deployment, and physical Pi installation are separate from the local demo. This task uses a bounded Modal training job authorized by Utsav.

## Verification

- The integrated frontend branch includes the API and detector code from `utsav/model`.
- API tests: 25 passed in the integrated frontend checkout.
- Detector pipeline tests: 8 passed in the integrated frontend checkout.
- Frontend: `pnpm build` passed; `pnpm lint` passed with two existing warnings.
- Browser: 5,170 cells, direct map-cell selection, all three display modes, five-site budget, model plan, four-series backtest, and demo-cell popup verified.
- A clearly identified local test event changed the demo cell from P(active) 0.04 to 0.08, showed one sighting, and updated its timestamp and posterior without reloading. Reset restored its prior and zero sightings.
- A test event on a real plan candidate (`892a100d467ffff`) moved it from rank 11 to rank 2 in both the API and frontend. The standard demo H3 is outside the model's candidate pool, so it updates the cell without claiming a pin moved.
- Test events were cleared from the isolated local API event file after verification.
- Offline recovery: three fixture sightings produced zero saved owls. Starting the API with one real test event replaced all three fixture sightings with that one event and one owl, restored all 5,170 model cells, and loaded the backtest. A second restart verified the event stream reconnects after a terminal HTTP error.
- Detector baseline: 54 reviewed training frames, 22 held-out frames; rat AP50 0.00755 in PyTorch and 0.01176 in ONNX. The failed candidate was preserved and was not promoted.
- Revised detector: 252 training frames, 49 validation frames from two whole clips. On identical square 416-pixel inputs, PyTorch and ONNX both have rat AP50 0.79031. Tabletop AP50 is 0.93674 on 22 frames; floor AP50 is 0.65108 on 27 frames. Raw outputs also match. This is a tabletop demo candidate; the combined 0.9 requirement and formal event gate are not passed. See `vision/TRAINING_RESULTS.md` for provenance and limits.
- Original recorded footage was replayed through the Pi detector rules on the Mac, using the 59–63 second segment of `zoom15_b`. One plush crop at confidence 0.860 passed the three-hit gate and received `accepted=true` from the API. The candidate cell score changed from 0.0923 to 0.1297 and its plan rank moved from 11 to 2. The frontend showed the crop and sighting. This recorded event remains in the isolated local demo state; canned test events were cleared.
- Physical Pi timing, camera exposure, and live prop success still require a test on the actual hardware.

## Handoff artifacts

- Editable five-slide deck: `pitch/out/barn-owl-three-minute-pitch-v8.pptx`; three-minute script: `pitch/script.md`.
- Local model bundle in the model worktree: `vision/runs/rat-litroom-candidate-20260926.zip` (25,624,553 bytes). SHA256: `63404725f343d020485c0ec8a8b3faca19d62cfbb5cb825eb28914cf3eeb89e0`. Includes the reviewed dataset, ONNX and PyTorch candidate, metrics, Pi runtime, checksums, and recorded replay evidence. Large training artifacts are ignored by Git.
- Recorded replay evidence in the model worktree: `vision/events/v2_live_demo/`, including `before.json`, `after.json`, `replay_report.json`, the plush crop, and `frontend.png`.
- Physical handoff: extract the bundle and follow its README for a room-lit, no-POST Pi check. Then measure the 20 timed pushes and three-minute negative reel described in `vision/RUNBOOK.md`. The overall box gate currently fails, so the candidate must not be represented as formally promoted or validated on live rats.
- Ethan's conversation is monitored every five minutes with a read-only background reader. No messages are sent.

## Run the integrated demo

In the `utsav/frontend` checkout, use separate terminals:

```sh
./api/run.sh
```

```sh
pnpm --dir web install --frozen-lockfile
pnpm --dir web dev
```

Open http://localhost:5173. The local API defaults to port 8000. `api/fake_event.sh` is a canned fallback for rehearsing the map interaction; disclose its use. The physical detector and saved-footage replay have separate validation requirements in `vision/RUNBOOK.md`.
