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
- Detector pipeline tests: 8 passed in the original integrated frontend checkout; expanded detector, verifier, and frame-handoff checks passed 20 tests in the model checkout before integration.
- Frontend: `pnpm build` passed; `pnpm lint` passed with two existing warnings.
- Browser: 5,170 cells, direct map-cell selection, all three display modes, five-site budget, model plan, four-series backtest, and demo-cell popup verified. After integrating teammate UI from `main`, local H3 search and external Times Square autocomplete opened cell details; the narrow layout was also checked. The merged frontend was pushed as `4d05b58` after build and lint checks.
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
- The locked v4 model and confidence 0.70 were evaluated once on 59 reviewed frames from four unused short recordings. PyTorch and ONNX matched at rat AP50 0.925806 and person AP50 0.876444. Full original-video replay emitted 20 events; reviewers found the plush in every event frame and crop, with no observed false event. The four clips are adjacent recordings from the same camera, table, and session as training, so this is a narrower generalization check than the separately captured new-room test. Event counts do not measure recall per push.
- On three post-lock new-room recordings, 439 reviewed frames yielded combined rat AP50 0.882675 and person AP50 0.343909. The rat result misses the 0.90 box target. At locked runtime confidence 0.70, 15 of 31 moving-plush ground-truth boxes matched. Original-video replay emitted nine plush events across four appearances and one false event on a black case; the first segment of the fourth appearance was missed until the plush reappeared. The parked plush had 137 ground-truth boxes but produced no 0.70-confidence proposals or events despite 0.994 AP at lower confidence. The 181.21-second negative clip replayed all 2,718 frames with zero events. These are recorded-scene results, not live Pi detection or independently timed pushes. V4 remains a candidate with known failures. The separate [new-room evaluation supplement](../vision/artifacts/rat-litroom-v4-new-room-evaluation-20260927.zip) is packaged, while the original v4 bundle remains unchanged.
- One bounded V5 run began at 02:46:25 UTC from the exact selected V4 checkpoint with frozen 652-frame training and 146-frame development validation sets. The V4 new-room clips were deliberately consumed as V5 development data. Epoch 35 was selected before full-video replay using the minimum rat AP50 across the three whole validation clips. Square-416 PT and ONNX matched: combined rat AP50 0.975279, person AP50 0.798870; the weakest whole clip was the moving new-room scene at rat AP50 0.960806. These are tuned development results, not a fresh post-V5 generalization test. See [V5 results](../vision/V5_RESULTS.md).
- V5 kept confidence 0.70 and the same event rules. All five complete development-video replays were independently checked against original frames: moving new-room 14 plush events, parked new-room 64 plush events, old metal 64, old floor 44, and the 181.206-second people-only clip zero. No other-object event appeared in those reviewed crops. The parked events came from one continuous exposure, not 64 pushes; the people-only clip was used in training, so its zero events are not an independent negative gate. On physical Pi saved frames, V5 made one plush proposal at confidence 0.931 and none on one negative frame, with about 60 ms median inference. Positive live-camera detection, API/map posting, formal 20-push recall, and a separate untouched three-minute negative test remain open. Ethan is working on fresh clips; an unidentified 92-second recording was excluded rather than scored.
- Original recorded footage was replayed through the Pi detector rules on the Mac, using the 59–63 second segment of `zoom15_b`. One plush crop at confidence 0.860 passed the three-hit gate and received `accepted=true` from the API. The candidate cell score changed from 0.0923 to 0.1297 and its plan rank moved from 11 to 2. The frontend showed the crop and sighting. This recorded event remains in the isolated local demo state; canned test events were cleared.
- Tailscale is installed with its network extension, and Utsav accepted the invitation to the shared Pi at `100.78.220.107`. SSH identified ARM64 with Python 3.13.5; the local alias is `barn-owl-pi`. On that physical Pi, isolated v4 inference from a saved frame had median latency 56.32 ms. After explicit approval, the optional bridge was enabled for one local-only live-worker trial: 2,052 frames at a mean 57.67 ms per frame, zero rat proposals with no plush presented, and no API posts. The worker was stopped while the camera feed remained active. This verifies throughput through the live frame path, not detection of a moving or parked plush on the Pi.

## Handoff artifacts

- The current editable three-minute pitch deck is `pitch/out/barn-owl-three-minute-pitch-v16.pptx`, with script at `pitch/script.md` and reviewed saved-event montage at `pitch/out/barn-owl-v5-development-replay-montage-v1.mp4`. They distinguish the V4 new-room failure from V5 tuned development results and keep the fresh test pending. The earlier API/map replay is labeled as V2; the montage shows saved V5 development-event stills. Older decks and training clips remain historical artifacts.
- The v4 candidate bundle is included in both Utsav branches as `vision/artifacts/rat-litroom-v4-candidate-20260927.zip` (91,067,807 bytes), SHA256 `8757ba863b0b20618f49b817059bec9a6af0d5d4268126f0f46e4704de4cecc7`. A clean extraction passed all 2,192 listed checksums and the sealed-test provenance check; the verifier is included in the archive. It contains the locked ONNX and PyTorch models, reviewed data, source and package lockfile, metrics, original videos, replay evidence, and Pi saved-frame timing. The bundled recheck command uses locked runtime confidence 0.70. See `vision/artifacts/README.md` and the extracted README for verification and the no-POST Pi command. This bundle is a lit metal-table plush demo candidate; it is not formally promoted.
- The V5 development candidate bundle is [rat-litroom-v5-development-candidate-20260927.zip](../vision/artifacts/rat-litroom-v5-development-candidate-20260927.zip) (94,422,665 bytes), SHA256 `5d4098dfea86dc80de230f9a689dad4ccdf819c194ac2ba5cdf96185bd5ca38e`. A clean extraction passed CRC, all 2,261 listed file checksums, and model/lock hash checks. It holds the selected epoch-35 PT/ONNX, frozen data fingerprints, training and verification records, reviewed development replay crops, and Pi saved-frame smoke test. It references the immutable V4 source videos by hash. Fresh independent testing is pending, and V5 has not replaced `vision/pi/rat.onnx`. See [V5 results](../vision/V5_RESULTS.md) and the [artifact index](../vision/artifacts/README.md).
- The earlier v2 ZIP, `vision/artifacts/rat-litroom-candidate-20260926.zip`, remains available as historical evidence. Its combined rat AP50 was 0.79031 and missed the box gate. Generated training runs remain ignored.
- Recorded replay evidence in the model worktree: `vision/events/v2_live_demo/`, including `before.json`, `after.json`, `replay_report.json`, the plush crop, and `frontend.png`.
- V4's same-session locked test and replay reports are under `vision/runs/modal-rat-v4-20260926/weak_test_once/` and inside the original bundle. The new-room results above belong to the packaged [separate supplement](../vision/artifacts/rat-litroom-v4-new-room-evaluation-20260927.zip), not that sealed bundle. A clean extraction passed its CRC and all 1,918 listed file hashes. The V5 bundle records adaptation to those now-consumed clips, with no fresh post-V5 test yet. The 20 independently timed pushes and positive live-camera/API/map test described in `vision/RUNBOOK.md` remain unmeasured. Live-rat performance remains unverified.
- An optional frame bridge and isolated Pi worker passed offline checks with the existing Owl agent unchanged. Following explicit approval, the bridge was enabled by one service restart for the local-only throughput trial described above. The worker has stopped and the camera feed remains active; end-to-end positive detection and event posting were outside that trial. See `vision/pi/LIVE_BRIDGE.md`.
- Ethan's conversation is monitored through active Computer Use with a five-minute background heartbeat. Concise project questions may be sent directly to Ethan under Utsav's authorization; the group chat remains read-only for the assistant.
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
