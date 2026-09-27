# NightOwl Pi detector code

The existing `/home/pi/barn-owl/agent.py` owns the Pi camera and dashboard stream. `vision/pi/detect.py` is a standalone camera program; do not start it beside that agent. The live integration uses the agent's JPEG callback, a separate ONNX worker, and an optional event relay. See [LIVE_BRIDGE.md](LIVE_BRIDGE.md) and the [observed V5 plush-to-map run](../V5_LIVE_RESULTS.md).

The earlier `world_rat_person.onnx` was a zero-training fallback for the
standalone detector. It is not tracked or used by the observed live path.
`vision/pi/rat.onnx` remains the separate deployment target; the V5 and V6
candidates have not replaced it.
The standalone `detect.py` CLI fails when a requested model is missing and
posts events only with `--post`. A bare model filename can resolve beside the
script; an explicit path must exist at that path. The older `--no-post` flag
still works for archived dry-run commands.

Paths and systemd names on the Pi still say `barn-owl`. They are deployment identifiers on that device, not the current team name.

| File | Job |
| --- | --- |
| `detect.py` | Grayscale 416 preprocessing, ONNX inference, class/person rules, and three-hit event gate; standalone camera CLI is optional |
| `live_bridge.py` | Nonblocking latest-JPEG handoff from the existing camera callback |
| `live_worker.py` | Separate ONNX process; writes local event JSON, crop JPEGs, and timing statistics |
| `event_relay.py` | Separate, dry-run-by-default delivery of saved `event_*.json` bodies to `/event` |
| `camera.py` | `rpicam-vid` capture for the standalone detector, with a mock-frame mode |
| `selftest.py`, `ir_check.py`, `grab_frames.py` | Isolated checks and frame capture tools |
| `bundle_wheels.sh`, `runtime-requirements.txt` | Offline ARM64 Python wheels for the detector process |

The isolated inference environment needs NumPy, OpenCV headless, and ONNX Runtime. It does not install PyTorch or Ultralytics on the Pi. The inspected Pi had aarch64, Python 3.13.5, and glibc 2.41. Recheck those versions before building wheels for another Pi. Keep the camera agent's system Python and service dependencies separate.

## Saved-frame compatibility check

Stage a *reviewed candidate* in its own `~/barn-owl-candidates/<model-hash>/` directory. Copy the matching ONNX, `detect.py`, `selftest.py`, `runtime-requirements.txt`, and two known saved JPEGs. Build wheels on the Mac with `bash vision/pi/bundle_wheels.sh 3.13`, then copy `vision/pi/wheels/` to that slot. On the Pi, verify `(cd wheels && sha256sum -c SHA256SUMS)` and the exact ONNX SHA before installing the isolated venv. `python3 -m venv --without-pip .venv` works when the Pi lacks system pip; use the bundled pip wheel with `PYTHONPATH` and `--no-index --find-links wheels` to install the pinned runtime requirements.

Run `.venv/bin/python selftest.py --only detector --model "$PWD/rat.onnx"` from the slot, then time inference on the saved positive and negative JPEGs. This reads files only. It does not open the camera, change the agent, call GPIO, or POST an event. V5's observed saved-frame median was about 60 ms; its later live worker processed 1,346 frames in 89.859 seconds, with mean inference 59.15 ms and one backlog drop. Those are measured on this Pi, not a guaranteed rate for another model or scene.

For the already staged V5 slot, this read-only check verifies the exact model
before the detector self-test. Confirm the SSH target and slot still exist:

```sh
ssh barn-owl-pi 'cd ~/barn-owl-candidates/v5-652a05e8 && sha256sum rat.onnx && ../v3-3214f2a0/.venv/bin/python selftest.py --only detector --model "$PWD/rat.onnx"'
```

Expected ONNX SHA256:
`652a05e8c08aaee11a2b4d3c9ae4c737387bf8ffcac3372a4d83d0df7d80ed3d`.

Do not copy a development candidate into `vision/pi/rat.onnx` because it passes this smoke check. V5 failed the [formal event test](../V5_FORMAL_EVENT_RESULTS.md), and V6 failed its [development regression limits](../V6_RESULTS.md). The Pi model path remains unchanged.

## Event contract

The worker saves the same nine-field event body used by the API. Example:

```json
{"node_id":"demo-01","h3":"892a100d2c3ffff","ts":"2026-09-26T21:04:11.302Z","class":"rat","conf":0.87,"n_hits":3,"bbox":[0.41,0.62,0.18,0.12],"crop_b64":"<jpeg>","fw":"0.1.0"}
```

`bbox` is normalized `[x, y, width, height]` from the top-left. `crop_b64` contains the rat crop JPEG, not the full camera frame. `event_relay.py` reads complete saved event bodies and requires explicit `--post` and `--api` before sending anything. A successful HTTP response can still say `accepted:false`; inspect that field and the relay receipt before claiming the map score changed. [LIVE_BRIDGE.md](LIVE_BRIDGE.md) has start, stop, receipt, and rollback details.
