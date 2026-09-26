# Pi 5 camera + PIR node — verification handoff

Status line in the README: **"Node hardware — verified 09-23, all four tests pass."** This file says
exactly what was run to earn that line, so anyone can re-run it in ten minutes and know whether the node
still works. Setup, login and networking are in `README-pi.md`; read that first if the Pi is boxed.

## What "verified 09-23, all four tests pass" means

On 2026-09-23, on the actual Pi 5 (Rev 1.1, Trixie 64-bit) with the IMX219 NoIR on CAM0, the HC-SR501 on
GPIO4 and one 850 nm board on a power bank, the four tests below were run in order and each produced the
expected output. It means: the camera is recognised and captures, the PIR reads and transitions, a PIR
edge triggers a still, and a video stream can be pulled from the camera in the format the detector wants.

It does **not** mean: the detector runs on the Pi (nothing was trained then and still is not), the
offline wheels install on this Pi (not attempted 09-23), the node is in an enclosure (D3 is not printed),
or the node is on a stable network (it was on flaky link-local Ethernet). Those are the hour-6 gate.

## Test 1 — camera still

```
rpicam-hello --list-cameras
rpicam-still --nopreview -t 1000 -o /tmp/still.jpg
ls -la /tmp/still.jpg
```

Expected:

```
Available cameras
-----------------
0 : imx219 [3280x2464 10-bit RGGB] (/base/axi/pcie@1000120000/rp1/i2c@88000/imx219@10)
    Modes: 'SRGGB10_CSI2P' : 640x480 [...] 1640x1232 [...] 1920x1080 [...] 3280x2464 [...]
```

then a ~1–3 MB `/tmp/still.jpg`, 3280×2464. `scp` it to the Mac and open it. In room light it looks
pink/magenta (see below). If `--list-cameras` prints `No cameras available!`, see `README-pi.md` §2.

## Test 2 — PIR read

```
python3 node/pir_test.py --pin 4 --seconds 30
```

Wave a hand in front of the module. Expected (timestamps are the Pi's clock, so possibly wrong):

```
pir_test: gpiozero backend, GPIO4, 30 s. Initial state: LOW
2026-09-23 15:04:11.203  HIGH  (motion)
2026-09-23 15:04:14.881  LOW   (held 3.68 s)
2026-09-23 15:04:19.550  HIGH  (motion)
2026-09-23 15:04:25.017  LOW   (held 5.47 s)
pir_test: done, 2 rising edges in 30 s
```

Hold time is the "time" pot. If it is stuck HIGH, wait 60 s for the module to settle, then turn the time
pot fully anticlockwise. If it never goes HIGH, check VCC is on 5 V (not 3.3 V) and OUT is on header
pin 7. If it toggles at a fixed rate with nothing moving, the IR board is probably shining into it (move
the board or the PIR).

## Test 3 — PIR-triggered IR capture

Room dark (lights off), IR board on its own bank and switched on, aimed at the same patch the camera sees.

```
python3 node/trigger_capture.py --count 3 --outdir captures/
```

Expected:

```
trigger_capture: gpiozero backend, GPIO4, count=3, debounce=2.0 s, outdir=captures
waiting for PIR...
2026-09-23 15:12:40  edge 1/3 -> captures/20260923-151240.jpg (1.91 MB, 2.4 s)
2026-09-23 15:12:51  edge 2/3 -> captures/20260923-151251.jpg (1.88 MB, 2.3 s)
2026-09-23 15:13:07  edge 3/3 -> captures/20260923-151307.jpg (1.93 MB, 2.4 s)
trigger_capture: done, 3 captures
```

The stills should be lit (a hand or the prop rat visible, background greyish-magenta) even though the
room is dark to the eye. If they are black, the IR board is off or pointed elsewhere; if they are pure
white, the board is too close (move it back or lower `--gain`). Run with `--dry-run` first to see the
`rpicam-still` command without touching the GPIO.

## Test 4 — video stream

This is the shape `vision/pi/camera.py` uses: raw YUV420, 640×480, 15 fps, fixed gain/shutter, greyworld
AWB, to stdout.

```
rpicam-vid -t 3000 --nopreview --codec yuv420 --width 640 --height 480 --framerate 15 \
  --gain 8 --shutter 30000 --awb greyworld -o - | wc -c
```

Expected: `20736000` (3 s × 15 fps × 460800 bytes per 640×480 YUV420 frame), give or take one frame
(`± 460800`). Anything that is not a multiple of 460800 means the pipe was cut mid-frame; anything much
smaller means the camera dropped frames and the shutter/gain is too demanding — drop to `--framerate 10`.
Then, on the Mac, `scp` a short file and view it:

```
rpicam-vid -t 3000 --nopreview --width 640 --height 480 --framerate 15 -o /tmp/test.h264
# on the Mac
ffplay /tmp/test.h264      # or open with VLC
```

## The magenta NoIR cast

A NoIR camera is a normal colour sensor with the IR-cut filter removed. The Bayer filter still splits
light into R/G/B pixels, but all three pass near-IR, and the red channel passes the most. Under 850 nm
light the sensor sees mostly "red + some blue", so the auto white balance (tuned for visible light) lands
on a strong **magenta/pink** cast; foliage and skin look pale and glowing. This is expected and correct.
It is not a wiring or overlay problem, and the camera is not broken.

What we do about it: `--awb greyworld` (a white-balance mode meant for NoIR that assumes the scene
averages to grey), and grayscale everywhere in the detector (`GRAY=True`), so the colour domain of
phone frames and rig frames is the same. Do not train on the magenta frames in colour and expect the
phone-footage model to transfer.

## IR board power

One 850 nm board, on its own USB power bank. Do not power it from the Pi's 5 V header or USB ports: it
under-volts the Pi (dmesg `Undervoltage detected`, lightning-bolt icon, camera timeouts). The Pi cannot
switch it; "is it on" is an image check (`vision/pi/ir_check.py` measures mean brightness of a frame)
or a look at the faint red glow. The 850 nm LEDs are visibly dim red in the dark, which is fine for a
demo (a 940 nm board would be invisible but needs ~2× the exposure; not worth it here). The board's
physical size is **not measured** (the enclosure tray assumes 21×29 mm, 10 mm lens); measure it before
the tray print. The plan said two boards; we have one, and one is enough for the diorama distance.

## How `captures/` was made

`captures/` in Bruno's repo (`~/div-hacks-26/captures/`, 25 JPEGs, committed there, **not in this repo**)
is the output of Test 3 run repeatedly on 09-23: room dark, one IR board on its bank ~40–60 cm from the
subject, camera at desk height, subject a hand / the prop rat / a shoe, with `rpicam-still` at the
options `trigger_capture.py` uses (gain 8, 30 ms shutter, greyworld AWB, 1640×1232). Filenames are
`YYYYMMDD-HHMMSS.jpg` from the Pi's clock, which was not NTP-synced, so the times are wrong by hours but
sort correctly. They exist to show (a) IR-lit exposure is workable at that distance, (b) the magenta
cast, (c) the prop's glass eye glints under IR — which is why the pitch's "eyeshine" line must be
worded so the demo crop does not contradict it.

## Re-verify checklist (event day, before the hour-6 gate)

1. Boot, ssh over static IP (`README-pi.md` §4a).
2. Test 1 (30 s). Test 2 (30 s). Test 3 with the IR board on (2 min). Test 4 (30 s).
3. `pip install --no-index --find-links wheels/ ...` in a venv, `python3 pi/selftest.py`.
4. `python3 pi/detect.py` with the YOLO-World fallback ONNX, watch for a POST.

If 1–2 pass and 3–4 do not, the node is still demoable as "PIR wakes the camera, capture goes to the
laptop, laptop runs the model". Say so at hour 6 rather than at hour 20.
