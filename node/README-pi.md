# Pi 5 node — setup, login, networking, gotchas

This is the setup side of the node workstream. The verification tests and what "verified 09-23" means
are in `HANDOFF-pi5-camera-pir-node.md`; this file is everything you need to get from a boxed Pi to a
shell prompt with a working camera and PIR, without internet.

## 1. Hardware

| Part | Detail | Where it plugs in |
|---|---|---|
| Raspberry Pi 5 Rev 1.1 | Debian 13 Trixie 64-bit (Raspberry Pi OS), Python 3.13 | — |
| Arducam IMX219 NoIR | 8 MP, no IR-cut filter, 22-pin ribbon | **CAM0** (the connector nearest the Ethernet jack). Needs a Pi 5 ribbon (22→15 pin); do not use the old 15-pin cable straight in |
| HC-SR501 PIR | passive infrared motion module | VCC → 5V (pin 2 or 4), GND → GND (pin 6), OUT → **GPIO4** (header pin 7) |
| 850 nm IR illuminator board | one board, powered from **its own USB power bank**, not the Pi | nothing on the Pi; see "IR board power" below |
| microSD | Trixie image | — |
| PSU | official 27 W USB-C recommended; a 5 V/3 A bank works for demos if the IR board is on its own bank | — |

**HC-SR501 notes.** OUT is 3.3 V when triggered, so it is safe on a Pi GPIO directly (the module runs
on 5 V internally but its output regulator is 3.3 V). Two pots: the one nearest the jumper is **time**
(how long OUT stays high, ~3 s to ~5 min), the other is **sensitivity** (range ~3–7 m). Turn time fully
anticlockwise for the shortest hold. The 3-pin jumper selects single trigger (H side off) vs
**repeat trigger** (H): with repeat, OUT stays high as long as motion continues; we use repeat. The module
needs ~30–60 s to settle after power-up and will fire a few spurious highs in that window; ignore them.

**IR board power.** The 850 nm board draws more than the Pi's 3.3 V/5 V header pins should supply
alongside the camera, and it brown-outs the Pi when shared. It gets its own power bank over USB. There is
no software control of it: "is the IR on" is checked by looking at a capture (`vision/pi/ir_check.py`
does this) or by the faint red glow of the LEDs.

## 2. Boot config

The IMX219 is not auto-detected on CAM0 on this image. Add to `/boot/firmware/config.txt`:

```
camera_auto_detect=0
dtoverlay=imx219,cam0
```

Then `sudo reboot`. Check with:

```
rpicam-hello --list-cameras
```

Expected: `0 : imx219 [3280x2464 10-bit RGGB] (/base/axi/pcie@1000120000/rp1/i2c@88000/imx219@10)`.
If it lists nothing, the ribbon is in backwards or in CAM1 (the overlay says `cam0`, so the connector
must match), or the overlay line has a typo. `camera_auto_detect=0` is required or the firmware keeps
looking for a camera on the other connector.

## 3. Login

Credentials (username, password, hostname) are in `CREDENTIALS.txt` in Bruno's repo, which is gitignored
and **not in this repo**. Ask Bruno. Do not paste them into chat or any committed file.

Once you have an address (see Networking):

```
ssh <user>@<pi-ip>
```

The Pi runs sshd on boot. mDNS (`<hostname>.local`) works over a direct cable or on the same switch
when both ends do link-local, but see below for why we do not rely on it.

## 4. Networking (the part that bites)

Facts:

- **The Pi has no internet.** Campus Wi-Fi is 802.1X (enterprise), and getting the Pi onto it needs a
  cert/credential flow we are not doing at the event. Assume the Pi never reaches the internet.
  Anything it needs (wheels, weights, scripts) goes over `scp`.
- **Direct Mac→Pi Ethernet is link-local only (169.254.x.x) and flaky.** Both ends have to fall back to
  APIPA, which takes 30–60 s, sometimes never happens on macOS after a sleep/wake, and the Pi's address
  changes. It worked on 09-23 but cost time every reconnect.
- **For the event: a small switch with DHCP, or static IPs on both ends.** Static is what we'll use.

### 4a. Static IPs, both ends (recommended)

Subnet `192.168.7.0/24`. Pi = `192.168.7.2`, Mac = `192.168.7.1`. No gateway, no DNS (nothing to reach).

**On the Pi** (needs one working session first — over link-local, or with a keyboard + HDMI):

```
# find the wired connection name (usually "Wired connection 1")
nmcli connection show

sudo nmcli connection modify "Wired connection 1" \
  ipv4.method manual \
  ipv4.addresses 192.168.7.2/24 \
  ipv4.gateway "" \
  ipv4.dns "" \
  ipv4.never-default yes

sudo nmcli connection down "Wired connection 1" && sudo nmcli connection up "Wired connection 1"
ip -4 addr show eth0     # expect inet 192.168.7.2/24
```

To go back to DHCP later: `sudo nmcli connection modify "Wired connection 1" ipv4.method auto ipv4.addresses ""`.

**On the Mac** (macOS System Settings):

1. System Settings → Network → pick the Ethernet adapter (USB-C/Thunderbolt Ethernet) → **Details…**
2. TCP/IP → Configure IPv4: **Manually**
3. IP address `192.168.7.1`, Subnet mask `255.255.255.0`, Router: leave **blank**
4. OK, then Apply.

Or from a terminal (the service name is whatever `networksetup -listallnetworkservices` prints for the adapter):

```
networksetup -listallnetworkservices
sudo networksetup -setmanual "USB 10/100/1000 LAN" 192.168.7.1 255.255.255.0
```

Then:

```
ping -c 3 192.168.7.2
ssh <user>@192.168.7.2
```

Leaving the router blank matters: with a router set, macOS may try to route internet through the dead
Ethernet link and your Mac loses Wi-Fi internet.

### 4b. Switch with DHCP (alternative)

Any travel router / switch with a DHCP server. Both ends on `ipv4.method auto`. Find the Pi with
`arp -a` on the Mac or the router's client list. Simpler cabling, one more box to carry and power.

### 4c. Copying files to the Pi

```
scp -r vision/pi/ <user>@192.168.7.2:~/pi/
scp -r node/       <user>@192.168.7.2:~/node/
```

## 5. Software on the Pi

**`picamera2` is not installed** on this image and cannot be installed offline (its dependency tree is
large and needs apt). Nothing in this project imports it. Everything that touches the camera shells out to
`rpicam-still` (stills) or `rpicam-vid` (streams), which are present and work.

Useful checks:

```
rpicam-hello --list-cameras
rpicam-still -o /tmp/test.jpg --nopreview -t 1000
rpicam-vid -t 5000 --codec yuv420 --width 640 --height 480 --framerate 15 -o /tmp/test.yuv --nopreview
python3 --version                     # 3.13.x on this image
python3 -c "import gpiozero; print(gpiozero.__version__)"
```

`gpiozero` ships with Raspberry Pi OS; `lgpio` is its Pi 5 backend. If `gpiozero` is missing for some
reason, `node/pir_test.py` falls back to `lgpio`, then to sysfs.

### Offline wheels

The Pi's Python is **3.13, aarch64**. The wheels in `vision/pi/wheels/` (onnxruntime, numpy,
opencv-python-headless and their deps) were downloaded on the Mac for that exact target and are not in
this repo (see the README, binary assets). Install with:

```
cd ~/pi
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install --no-index --find-links wheels/ onnxruntime numpy opencv-python-headless
```

`--system-site-packages` so the venv still sees `gpiozero`/`lgpio` from apt. `--no-index` so pip does not
try (and hang) reaching PyPI. If `python3 --version` on the Pi is not 3.13, the wheels will not install;
rebuild them on the Mac with `vision/pi/bundle_wheels.sh <version>` and re-copy.

## 6. Running the node scripts

```
python3 node/pir_test.py --seconds 30            # watch PIR transitions
python3 node/trigger_capture.py --count 5        # 5 PIR-triggered IR stills into captures/
python3 node/trigger_capture.py --dry-run        # print the rpicam-still command, no hardware needed
```

Then the vision side: `python3 pi/selftest.py`, `python3 pi/ir_check.py`, `python3 pi/detect.py`
(see `vision/RUNBOOK.md`).

## 7. Gotchas

- **`dtoverlay=imx219,cam0` and `camera_auto_detect=0`**, both, in `/boot/firmware/config.txt` (not
  `/boot/config.txt`; on Trixie that path is a leftover).
- **Ribbon orientation**: contacts face the connector's contacts; on the Pi 5 the blue tab faces the
  Ethernet/USB side on CAM0. A backwards ribbon lists no camera and does no harm.
- **Magenta/pink images are correct.** NoIR + IR light = a strong magenta cast. `--awb greyworld`
  tames it; the detector runs grayscale anyway. Do not "fix" the camera.
- **PIR settles for ~60 s** after power. Spurious triggers in that window are normal.
- **PIR does not detect rats reliably** (small, low body-heat signature at rail distance). It gates the
  camera to save power and gives a wake-up; the detector decides. Do not claim otherwise in the pitch.
- **IR board on its own bank.** Sharing power with the Pi causes under-voltage (lightning bolt / dmesg
  `Undervoltage detected`) and camera timeouts.
- **Link-local Ethernet drops after the Mac sleeps.** Set static IPs (§4a) once and stop fighting it.
- **`picamera2` absent, `pip` offline.** Any script that does `import picamera2` or `pip install x`
  without `--no-index` is a script written for a different Pi.
- **Python version must match the wheels** (3.13 aarch64). Check before scp.
- **`rpicam-still` first-frame delay.** Default `-t 5000` waits 5 s for AE/AWB. Use `-t 1000` or
  `--immediate` for fast triggers; expect the first frame after boot to be darker.
- **The camera holds `/dev/video*`**: only one `rpicam-*` process at a time. `trigger_capture.py` and
  `camera.py` (the stream) cannot run together; kill one first.
- **GPIO4 is also 1-Wire's default pin.** Make sure `dtoverlay=w1-gpio` is *not* in config.txt.
- **Time is wrong on the Pi** (no NTP without internet). Set it after connecting so capture filenames
  sort: `sudo date -s "$(date -u +'%Y-%m-%d %H:%M:%S')"` from a Mac shell over ssh, or accept UTC drift.
