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
- The v2 detector used 252 training frames and 49 validation frames from two whole clips. On identical square 416-pixel inputs, PyTorch and ONNX both reached rat AP50 0.79031. Tabletop AP50 was 0.93674 on 22 frames; floor AP50 was 0.65108 on 27 frames. That candidate missed the combined 0.9 box gate and remains in the tracked handoff bundle as a historical demo candidate.
- The locked v3 checkpoint used 414 reviewed training frames; the same 49 whole-clip validation frames were kept out of training. Local CPU verification on square 416-pixel inputs measured rat AP50 0.943296 overall, 0.995 on the metal table and 0.817 on the floor, plus person AP50 0.903235. PyTorch and ONNX AP50 matched. This passes the combined rat box gate on validation, but those clips were repeatedly used to choose the recipe and checkpoint. Training-data review also found some person boxes in short clips 23–26 include chair fabric. See `vision/HILL_CLIMB.md` and `vision/TRAINING_RESULTS.md` in the model branch for provenance.
- The v3 checkpoint replayed the two full validation videos through Pi inference and event rules without posting to the API. It emitted 63 metal-table and 47 floor events; all 110 saved crops were visually reviewed and contained the plush. This is tuned-validation replay evidence, not an independent estimate of event precision.
- The one-time locked v3 test used 186 reviewed frames from four whole recordings outside training and checkpoint selection. PyTorch and ONNX both measured combined rat AP50 0.870308 and person AP50 0.304945. The 111-second fresh-angle plush clip scored rat AP50 0.844166 and person AP50 0.130979. At locked Pi settings, full-video replay produced 39 events on that fresh clip, 14 of them on chair fabric, and one chair false alert in a 46.92-second empty clip. V3 failed the independent test and was not published. These four recordings became consumed development evidence for v4.
- V4 corrected 36 broad training person boxes and added the consumed fresh positive and empty recordings, for 572 reviewed training frames. It completed 150 epochs. On the repeatedly used 49-frame development validation set, PyTorch and ONNX agreed at rat AP50 0.958333 and person AP50 0.863095. Full development-video replay revealed six stationary-object false events at confidence 0.50; confidence 0.70 was selected on development footage before the next test, without changing the weights or event rules.
- The locked v4 model and confidence 0.70 were evaluated once on 59 reviewed frames from four unused short recordings. PyTorch and ONNX matched at rat AP50 0.925806 and person AP50 0.876444. Full original-video replay emitted 20 events; reviewers found the plush in every event frame and crop, with no observed false event. The four clips are adjacent recordings from the same camera, table, and session as training, so this is a narrower generalization check than a new-room test. Event counts do not measure recall per push. The model still needs a live-camera accuracy check, verified push times, and the three-minute negative reel.
- Original recorded footage was replayed through the Pi detector rules on the Mac, using the 59–63 second segment of `zoom15_b`. One plush crop at confidence 0.860 passed the three-hit gate and received `accepted=true` from the API. The candidate cell score changed from 0.0923 to 0.1297 and its plan rank moved from 11 to 2. The frontend showed the crop and sighting. This recorded event remains in the isolated local demo state; canned test events were cleared.
- Tailscale is installed with its network extension, and Utsav accepted the invitation to the shared Pi at `100.78.220.107`. SSH identified ARM64 with Python 3.13.5; the local alias is `barn-owl-pi`. On that physical Pi, isolated v4 inference from a saved frame had median latency 56.32 ms. This does not verify the live camera, event timing, exposure, or moving prop. The upload app recovered through its admin route and two post-lock new-room clips were received. Truth review is in progress without changing the locked model. One clip includes a parked plush, so the three-minute negative recording needs to be redone.

## Handoff artifacts

- The editable three-minute pitch deck is `pitch/out/barn-owl-three-minute-pitch-v13.pptx`, with speaker script at `pitch/script.md` and training video at `pitch/out/barn-owl-training-demo-v3.mp4` in the model branch. They use the v4 same-session reserve result, rat AP50 0.926 on 59 reviewed frames, and leave new-room and live-camera tests pending. The earlier recorded-footage replay is labeled as v2.
- The v4 candidate bundle is committed locally in the model branch as `vision/artifacts/rat-litroom-v4-candidate-20260927.zip` (91,067,807 bytes), SHA256 `8757ba863b0b20618f49b817059bec9a6af0d5d4268126f0f46e4704de4cecc7`. A clean extraction passed checksums for all 2,192 included files other than the verifier itself and the sealed-test provenance check. It contains the locked ONNX and PyTorch models, reviewed data, source and package lockfile, metrics, original videos, replay evidence, and Pi saved-frame timing. The bundled recheck command uses locked runtime confidence 0.70. See `vision/artifacts/README.md` and the extracted README for verification and the no-POST Pi command. This bundle is a lit metal-table plush demo candidate; it is not formally promoted.
- The earlier v2 ZIP, `vision/artifacts/rat-litroom-candidate-20260926.zip`, remains the remote handoff until the v4 branch is reviewed and integrated. Its combined rat AP50 was 0.79031 and missed the box gate. Generated training runs remain ignored.
- Recorded replay evidence in the model worktree: `vision/events/v2_live_demo/`, including `before.json`, `after.json`, `replay_report.json`, the plush crop, and `frontend.png`.
- V4's locked test and replay reports are under `vision/runs/modal-rat-v4-20260926/weak_test_once/` in the model worktree and inside the bundle. The 20 timed pushes and three-minute negative reel described in `vision/RUNBOOK.md` still need measurement on the Pi. Live camera operation, a new-room test, and live-rat performance also remain unverified.
- An optional frame bridge and isolated Pi worker passed offline checks with the existing Owl agent unchanged. The bridge is off by default; enabling it on the live agent is pending user approval and a supervised trial. See `vision/pi/LIVE_BRIDGE.md`.
- Ethan's conversation is monitored every five minutes. Project questions are authorized when needed; Utsav handles outgoing messages.
- The DivHacks group chat contains nine hardware photos and five videos from Sanjavan. They document the physical setup but do not establish detector performance or a successful Pi run.

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
