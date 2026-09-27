# Night Owl vision runbook

The detector recognizes a dark plush rat and people in lit camera footage. It is a prototype for the Night Owl demo, not a validated live-rat alarm. Older artifact names and environment variables still use `barn-owl`; keep those names when running the code.

## Current result

- **V5 is the locked demo candidate**, at confidence 0.70. Its fresh box test measured rat AP50 0.615779, with a known reference-box quality problem. Its separate fixed event test matched 18 of 19 reviewed plush appearances but fired 17 times in 190.409 seconds of no-plush footage, or 5.357 false events per minute. The event test failed. See [V5 fresh results](V5_FRESH_RESULTS.md) and [V5 formal event results](V5_FORMAL_EVENT_RESULTS.md).
- **The live path worked once with the plush.** The Pi camera handoff processed 1,346 frames in 89.859 seconds, saved six crops of one visible plush exposure, and relayed one event to the local API. The map recorded the accepted sighting. The worker and relay stopped afterward. See [V5 live results](V5_LIVE_RESULTS.md).
- **V6 was rejected after training.** Its development rat AP50 was 0.964575 combined, but the floor clip and person-class regression limits failed. No consumed formal replay or Pi model switch followed. See [V6 results](V6_RESULTS.md). The V5 and V6 models have not been promoted to `pi/rat.onnx`.

For a supervised demo, use a lit scene and keep the whole plush in view. Say that the live integration was observed once; do not present the repeated crops as six pushes or the failed formal test as a pass.

## Local setup

From the repository root:

```sh
cd vision
uv sync --locked --python 3.11
. .venv/bin/activate
```

The CPU evaluation lock pins NumPy 2.4.6, OpenCV Python 5.0.0.93, PyTorch 2.14.0, TorchVision 0.29.0, Ultralytics 8.4.163, and ONNX Runtime 1.22.1. Modal's training image uses PyTorch 2.8.0; [MODAL.md](MODAL.md) describes that separate environment. Training videos, labels, datasets, ONNX files, and run reports are ignored by Git. The tracked result notes link to their delivered evidence archives.

## Inspect the locked V5 candidate

The selected ONNX is `vision/runs/modal-rat-v5-20260927/rat.onnx`, SHA256 `652a05e8c08aaee11a2b4d3c9ae4c737387bf8ffcac3372a4d83d0df7d80ed3d`. Its source lock is `vision/runs/modal-rat-v5-20260927/candidate_lock.json`, SHA256 `22ffcee2d241eb0c016d0a3ae5d178ef8d35e1f6541d1b20674f2c9a81237259`. The unchanged runtime uses grayscale 416, NMS 0.45, floor cutoff 0, rat width 0.01–0.65, person suppression IoU 0.3/containment 0.7, three consecutive hits in one second, and a two-second cooldown.

For a *development* check on the same whole clips used to select V5, run:

```sh
vision/.venv/bin/python vision/verify_candidate.py \
  --dataset vision/runs/modal-rat-v5-20260927/dataset \
  --pt vision/runs/modal-rat-v5-20260927/best.pt \
  --onnx vision/runs/modal-rat-v5-20260927/rat.onnx \
  --runtime-conf 0.70 \
  --out-dir vision/runs/modal-rat-v5-20260927/diagnostics/new-local-check
```

Use a new output directory. The verifier reports square-416 CPU PT and ONNX AP50 at confidence 0.001 and NMS IoU 0.7, then checks the Pi parser separately at runtime confidence 0.70. These validation clips were used for model selection. They are not a fresh test, and sampled frames cannot measure push events.

For a full recorded-video replay without posting to the API:

```sh
vision/.venv/bin/python vision/replay_video.py \
  --clip vision/clips/zoom15_b.mp4 \
  --model vision/runs/modal-rat-v5-20260927/rat.onnx \
  --conf 0.70 --iou 0.45 --floor-y 0 \
  --person-iou 0.3 --person-contain 0.7 \
  --hits 3 --window 1 --cooldown 2 --no-pace \
  --save-events vision/events/v5-local-check \
  --json vision/events/v5-local-check/report.json
```

Replay reads every decoded frame and its source timestamp. A second run on the same clip is development inspection, not another independent test. Do not turn sparse `frames/_sources.csv` sample times into push ground truth; those times are nominal extraction positions.

## New footage and future testing

[RECORDING.md](RECORDING.md) gives the capture and source-review protocol. Keep whole recording sessions in one split. Freeze source hashes, visible-plush boxes, person boxes, push intervals, and a separate no-plush clip before running a new model on them. An empty label file requires visual review of the entire frame. The formal event target needs at least 20 distinct reviewed pushes, at least 18 matched events, and fewer than 0.5 false events per minute over a separate no-plush recording of at least three minutes. Review every emitted crop against its native source frame. Repeated cooldown events from one exposure count as one matched push.

`verify_candidate.py --test-set` is for a sealed, test-only frame snapshot. It requires the exact ONNX SHA256 and `--selection-dataset` so it can check source overlap and provenance before AP scoring. A no-plush clip has undefined rat AP50; replay its complete original video for false-event counts. A new reserved session is required to assess any model adapted to the consumed V5 formal recordings.

Do not adjust the locked threshold, floor rule, region of interest, labels, or checkpoint after seeing a test result and then call the same footage fresh. The V6 recovery run kept those boundaries: its failed regression candidate was saved, with no formal replay or Pi switch.

## Pi and map path

The existing Pi camera agent owns the camera. [pi/LIVE_BRIDGE.md](pi/LIVE_BRIDGE.md) describes its default-off frame handoff, the separate ONNX worker, and the optional relay for saved event JSON. `live_worker.py` saves events locally; it does not post or drive an LED. `event_relay.py` is dry-run by default and needs an explicit API destination and `--post`. The accepted V5 relay event and local map update are recorded in [V5 live results](V5_LIVE_RESULTS.md). Do not start `pi/detect.py` beside the camera agent, because that program opens its own camera.

The API reads `BARN_OWL_MIN_CONF` at startup. If a future approved model uses a different confidence, align that value with the detector and restart the API before posting. HTTP 200 only shows that the API handled the request; inspect its `accepted` field and the stored posterior to confirm a score update.
