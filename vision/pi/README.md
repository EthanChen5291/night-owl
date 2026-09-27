# Node software (`vision/pi/`)

Everything in this directory runs on the Pi 5 with **numpy + opencv-python-headless + onnxruntime**
only. No ultralytics, no picamera2 (not installed, see the repo README §4), no internet (802.1X
Wi-Fi), so the wheels travel with the code and the camera is driven through `rpicam-vid`.

| File | What |
|---|---|
| `camera.py` | `rpicam-vid` raw YUV420 → numpy frames (Y plane = grayscale); `--mock DIR` for the Mac |
| `detect.py` | the node: letterbox → ONNX → NMS → floor rule → person suppression → 3 hits → event → POST `/event` → LED |
| `grab_frames.py` | save rig frames for training / eval (`--seconds`, `--every`) |
| `selftest.py` | system / camera / stream / PIR / detector, PASS/FAIL each |
| `ir_check.py` | is the 850 nm illuminator on (mean luminance + centre hotspot) |
| `bundle_wheels.sh` | `pip download` aarch64 wheels for a given Python version into `wheels/` |
| `rat.onnx` | our detector (from `../train.sh`); **gitignored**, copy it here |
| `world_rat_person.onnx` | YOLO-World zero-training fallback ("stuffed animal", "person"); not in git, ~50 MB |
| `wheels/` | offline wheels; **gitignored** |

## Isolated candidate smoke on the Pi

The candidate can be checked without using the camera, posting to the API, or replacing the
running Owl agent. These commands stage files under a new home-directory slot. Run them only
after SSH is stable. Set `PI_TARGET` to the reachable Pi SSH address; the example candidate
hash is for the expanded V3 export. V3 failed the independent test because it repeatedly
mistook a chair for the plush. Use this example only to check Pi package compatibility and
inference speed while the next candidate is prepared; it is not a demo model.

```sh
PI_TARGET=pi@<pi-address>
SLOT=barn-owl-candidates/v3-3214f2a0
bash vision/pi/bundle_wheels.sh 3.13  # on the Mac; pinned aarch64 wheels from PyPI
ssh "$PI_TARGET" 'uname -m; python3 --version; ldd --version | head -1'
ssh "$PI_TARGET" 'mkdir -p "$HOME/barn-owl-candidates/v3-3214f2a0"'
scp vision/pi/{detect.py,selftest.py,camera.py,runtime-requirements.txt} "$PI_TARGET:$SLOT/"
scp vision/runs/modal-rat-v3-expanded-20260926/rat.onnx "$PI_TARGET:$SLOT/rat.onnx"
scp vision/runs/modal-rat-v3-expanded-20260926/dataset/images/val/zoom15_b_00013.jpg "$PI_TARGET:$SLOT/positive.jpg"
scp vision/runs/modal-rat-v3-expanded-20260926/dataset/images/val/zoom15_b_00000.jpg "$PI_TARGET:$SLOT/negative.jpg"
scp -r vision/pi/wheels "$PI_TARGET:$SLOT/"
```

`vision/pi/wheels/` is about 75 MB; each individual wheel is under 100 MB. The runtime
requirements are only NumPy, OpenCV headless, and ONNX Runtime. The Mac evaluator's PyTorch,
TorchVision, and Ultralytics dependencies are not installed on the Pi. This bundle targets
Python 3.13 aarch64 and glibc at least 2.28; the Pi inspected on 2026-09-26 had Debian 13,
glibc 2.41, and Python 3.13.5. If its interpreter or architecture changes, rebuild the wheels
before installing. If `venv` is unavailable, stop here and arrange a separate setup step.

```sh
ssh "$PI_TARGET" 'cd "$HOME/barn-owl-candidates/v3-3214f2a0" && (cd wheels && sha256sum -c SHA256SUMS) && sha256sum rat.onnx'
# Expected model SHA256: 3214f2a0dbe1699016b8f4e8aaa8d4c7c5eb3d5e365a07f26a2efbe13114672b
ssh "$PI_TARGET" 'cd "$HOME/barn-owl-candidates/v3-3214f2a0" && python3 -m venv --without-pip .venv && PIP_WHEEL=$(find wheels -maxdepth 1 -name "pip-*.whl" -print -quit) && PYTHONPATH="$PWD/$PIP_WHEEL" .venv/bin/python -m pip install --no-index --find-links "$PWD/wheels" -r runtime-requirements.txt'
ssh "$PI_TARGET" 'cd "$HOME/barn-owl-candidates/v3-3214f2a0" && .venv/bin/python selftest.py --only detector --model "$PWD/rat.onnx"'
```

The detector self-test runs a zero frame. For a representative saved-frame timing and the
rat/person rule result, run the following from the Mac. It reads the two staged JPEGs and
does not import `camera.py` or initialize GPIO:

```sh
ssh "$PI_TARGET" 'cd "$HOME/barn-owl-candidates/v3-3214f2a0" && .venv/bin/python -' <<'PY'
import cv2
import statistics
import time
from detect import Detector, apply_rules

detector = Detector("rat.onnx", gray=True, conf=0.5, iou=0.45)
for name in ("positive.jpg", "negative.jpg"):
    image = cv2.imread(name, cv2.IMREAD_GRAYSCALE)
    assert image is not None and image.shape == (480, 640), name
    for _ in range(3):
        detector.infer(image)
    durations = []
    for _ in range(20):
        start = time.perf_counter()
        detections = detector.infer(image)
        durations.append((time.perf_counter() - start) * 1000)
    rats, persons = apply_rules(detections, floor_y=0)
    print(name, "median_ms", round(statistics.median(durations), 1),
          "p95_ms", round(sorted(durations)[18], 1),
          "rats", len(rats), "persons", len(persons),
          "top_rat_conf", round(rats[0].conf, 3) if rats else None)
PY
```

Keep `~/barn-owl/agent.py`, its model, service, camera, and API untouched until a separate
deployment decision. Saved-frame timing checks ONNX Runtime compatibility and CPU speed;
it does not validate camera capture or real event recall.

## Setup, in order

1. **Wheels on the Mac** (once, for the Pi's Python; it was 3.13 on 09-23):
   `./bundle_wheels.sh 3.13`
2. **Copy** (static IPs both ends; see below):
   `scp -r vision/pi pi@192.168.7.2:~/pi`
3. **Install on the Pi**:
   ```
   cd ~/pi
   python3 -m venv --system-site-packages ~/venv && . ~/venv/bin/activate
   pip install --no-index --find-links wheels/ onnxruntime numpy opencv-python-headless
   ```
   `--system-site-packages` keeps apt's `gpiozero`/`lgpio` (LED, PIR) visible inside the venv.
4. **Self-test**: `python3 selftest.py` — five PASS lines. `system` FAIL with a wheels/interpreter
   mismatch means step 1 with the other version. `camera` FAIL: `dtoverlay=imx219,cam0` in
   `/boot/firmware/config.txt`, ribbon in CAM0, reboot.
5. **IR**: `python3 ir_check.py` with the room light off. Wants `IR ON`.
6. **Detector**, fallback first (the hour-6 gate does not wait for training):
   `python3 detect.py --model world_rat_person.onnx --color --no-post`
   then with the server: `BARN_OWL_API=http://192.168.7.1:8000 python3 detect.py --model world_rat_person.onnx --color --save-events events`
   The World model fires on hoodies and bags and runs ~4× slower; that is expected, it is the
   fallback. When `rat.onnx` arrives: `python3 detect.py` (defaults: `rat.onnx`, grayscale).
7. **Rig clips for training** (RECORDING.md "Once you get there"):
   `python3 grab_frames.py --out rig/hall_a --tag hall_a --seconds 60 --every 5`, then
   `scp -r pi@192.168.7.2:~/pi/rig/hall_a vision/frames_rig/`.

## Network

Direct Mac→Pi Ethernet is link-local only and flaky (README §4). Use a switch with DHCP, or
static IPs both ends:

- Pi: `sudo nmcli con mod "Wired connection 1" ipv4.method manual ipv4.addresses 192.168.7.2/24 && sudo nmcli con up "Wired connection 1"`
- Mac: System Settings → Network → the USB/Ethernet adapter → Configure IPv4 Manually, `192.168.7.1`, mask `255.255.255.0`.
- Server on the Mac at `http://192.168.7.1:8000` (that is `detect.py`'s default `API_URL`).
- `ping 192.168.7.2` from the Mac before every demo run. Login is in `CREDENTIALS.txt` (ask Bruno).

## Flags you will actually use

`detect.py --show` (Mac only, draws boxes; the grey line is `FLOOR_Y`), `--no-post`, `--save-events DIR`,
`--conf 0.4`, `--mock ../frames --max-frames 300`, `--model`, `--color`, `--names a,b` for an
unknown model. All constants (`CONF`, `FLOOR_Y`, `HITS_NEEDED`, `EVENT_COOLDOWN_S`, `NODE_ID`,
`DEMO_H3`, `LED_PIN`) are at the top of `detect.py` and each has a flag.

## Event body (frozen contract)

```json
{"node_id":"demo-01","h3":"892a100d2c3ffff","ts":"2026-09-26T21:04:11.302Z","class":"rat",
 "conf":0.87,"n_hits":3,"bbox":[0.41,0.62,0.18,0.12],"crop_b64":"<jpeg>","fw":"0.1.0"}
```

`bbox` is `[x, y, w, h]` normalised, top-left origin. `crop_b64` is the rat crop only (≤160 px,
JPEG q80, a few KB); the full frame never leaves the node.
