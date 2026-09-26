# Node as built (photos, Saturday 2026-09-26)

Bruno's print is done and the node runs. Four photos of the assembled unit were taken at the venue; this
records where the build departs from `D3_NOTES.md` and the CAD so nobody "fixes" it back.

## What matches the D3 design

- Face-down D3 body: frosted PETG tray with the three sensors flat on the face, black end caps top and
  bottom, Pi standing inside behind the tray, visible from the side.
- Sensor order on the face, top to bottom: 850 nm IR illuminator (round lens, its own small dome indicator
  on top), IMX219 NoIR camera module (green tab is the ribbon side), HC-SR501 PIR under its white Fresnel
  dome. Same axis, same order as `MEASUREMENTS.md` (IR y=18.1, cam y=44.1, PIR y=75.6).
- Two columns of hexagonal vents either side of the sensor strip (the feather-comb vents from the owl
  variant, so the printed tray is the owl tray, not the plain D3 tray).
- Hanger arm plate on one side with a thumbscrew.

## What differs

| Design | As built | Why it matters |
|---|---|---|
| Boards held by printed fences + hot glue | Each board is lashed with a loop of white wire threaded through the hex vents (IR: one loop; camera: one loop; PIR: one loop under the dome) | Fences alone did not retain the boards; the wire is load-bearing. Do not remove for "tidiness" before the demo. |
| M4×30 + nut pivot, 2× M3×8 sector plate | Black knurled thumbscrew into the arm plate; a second thumbscrew visible on the far side | Tilt is set by hand. Check it is tight before the stage: the box swings if loose. |
| L-arm with V-groove foot on a tree-guard rail | Two black gooseneck arms come out of the bottom of the box (flexible stand) | The demo rig is a desk/diorama gooseneck, not the rail hanger. Rail hanger parts stay in the STL folder for the situ story. |
| Power from a PiSugar or USB bank at the base | USB-C cable into the Pi from the top-rear, plus a white cable to the IR board | Two cables leave the box; route them so they do not enter the camera's field of view when face-down. |
| Wi-Fi/none | USB-C to Ethernet adapter on the Mac side (green link LED) with a white Cat5 to the Pi | Confirms the wired plan. Static IPs: Pi 192.168.7.2, Mac 192.168.7.1, API `http://192.168.7.1:8000`. |
| Lid 1 mm clear PETG | Side is open/translucent enough that the Pi's blue activity LED shows through as a blue streak | Free "it's alive" indicator on stage; the cyan band glow in the renders is still demo-only. |
| Owl "facial disc" recess | Not printed (flat tray face) | Cosmetic only. |

## Things to verify with the unit in hand

1. IR board dimensions (`led_board`, `led_lens_d`): the board is now mounted, so measure it through the
   vents or note that the 10 mm lens hole fits. Close the "UNMEASURED" flag in `MEASUREMENTS.md`.
2. Whether the IR lens sits proud of the tray face (it looks ~4 mm proud in the photos): if so it will
   scatter into the camera when face-down on a light floor. `pi/ir_check.py` tells you.
3. The PIR dome is the widest thing on the face and its edge is within ~10 mm of the camera lens: the
   camera's field of view might clip it at 62°. Take one `rpicam-still` and look for a bright arc at the
   bottom of frame.
4. Tilt setting of the gooseneck for the diorama: use the 45° row in `aim-coverage.png`.
