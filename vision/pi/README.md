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
