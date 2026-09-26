# D3 print and assembly

Files: `~/div-hacks-26/enclosure/stl/d3_{body,lid,tray}.stl`, `hanger_{arm,sector,pin}.stl` (exported
2026-09-25 15:20). Nothing has been printed yet. Dimensions in `MEASUREMENTS.md`; model notes in
`HANDOFF-D3.md`; coverage vs tilt in `aim-coverage.png`.

## Before the first print

Measure the real 850 nm IR board: its outline, the LED lens diameter and where the lens sits relative to
the board centre. The tray is cut for a 21 × 29 mm board with a 10 mm lens at centre (`led_board`,
`led_lens_d`, `led_lens_off` at node_d3.scad:31–33) and nobody has checked that. The v2 file drew the same
part with a 19 mm barrel, so expect the hole to change. Fix the numbers, re-run `./build_d3.sh`, then print.

## Print order

1. **Tray** (`d3_tray.stl`, frosted PETG, ~25 min). Print it first and alone. Drop the camera, PIR and IR
   boards into their fences: each should sit flat with the lens holder, dome and LED through their holes and
   no more than about 0.3 mm of side play. The camera ribbon must exit through the open side of its fence
   (toward the port side). If a board does not drop in, change its `*_board` value and reprint; nothing
   else depends on the tray except `deck_z`, which does not change unless `sensor_depth` or `tray_t` do.
2. **Body** (`d3_body.stl`, black PLA, ~1.5 h). Deck down, open top up, as exported.
3. **Lid** (`d3_lid.stl`, clear PETG, ~35 min). Top face on the plate, as exported.
4. **Sector** and **arm** (`hanger_sector.stl`, `hanger_arm.stl`, black PLA, ~30 min together). Flat.
5. **Pin** (`hanger_pin.stl`) only if you have no spare M4 bolt, nail or 4 mm hex key.

## Materials and settings

| Part | Material | Layers | Perimeters | Infill | Notes |
|---|---|---|---|---|---|
| tray | frosted PETG (clear PETG if that is what is on hand) | 0.28 | 2 | 10 % | face down; the 21 mm skirt is the glowing band |
| body | black PLA | 0.28 | 2 | 10 % | no supports; vents and openings are through-walls |
| lid | clear PETG | 0.20 | 2 | 100 % | 1.0 mm thick so the Pi shows through; do not thicken past ~1.2 |
| sector | black PLA | 0.28 | 2 | 10 % | |
| arm | black PLA, PETG for outdoors | 0.28 | **3** | 10 % | takes the whole load |
| pin | anything | 0.28 | | | optional |

No supports anywhere: the skirts sit outside the body and every hole is vertical in print orientation.
Glue stick on the plate for PETG. PLA does not bond to PETG, which is fine here: the tray and lid are
friction fits (0.2 mm per side) and a dab of hot glue at two corners holds them if loose.

## Hardware

| Qty | Item | Where |
|---|---|---|
| 1 | M4 × 30 bolt + nut | pivot: through arm (6) + sector (4) + wall (1.6); nut inside the cable bay |
| 1 | M4 bolt / nail / 4 mm hex key, or the printed pin | index pin, 4.4 mm holes |
| 2 | M3 × 8 | sector plate to the wall (3.2 mm clearance holes), optional; the pivot bolt alone holds |
| 2 | M3 × 8 | lid to the two corner posts (2.6 mm self-tap), optional |
| 2 | zip ties (≤ 4.5 mm wide) | through the foot slots, over the rail |
| — | hot glue | one corner of each sensor board; tray/lid corners if loose |

## Assembly

1. **Tray.** Lay each board flat in its fence: camera lens holder through the 12.5 mm hole with the
   ribbon edge toward the open side (port side, −y); PIR dome through the 24 mm hole; IR LED through the
   small hole with the photoresistor left behind the plastic (it reads dark, so the LED stays on). Hot-glue
   one corner of each.
2. **Body onto tray.** Feed the camera ribbon, the PIR wires and the IR lead up through the 32 × 7 mm slot
   in the deck beside the camera. The IR lead goes on out through the notch in the tray's rear skirt. Push
   the body down into the tray's skirt until the deck seats at 15.2 mm.
3. **Pi stack.** Drop the Pi 5 + PiSugar stack onto the four stud sockets, microSD end toward the front
   (engraved "SB-01" wall), USB-C/HDMI edge toward the side window ("PI 5 · PORTS THIS SIDE" is engraved in
   the deck). Ribbon into CAM0. PIR: VCC to 5 V (pin 2), GND (pin 6), OUT to GPIO4 (pin 7). Battery variant:
   the pack sits in the fences and the stack rests on it.
4. **Sector plate** on the wall marked "ARM SIDE": M4 bolt through arm leg, sector and wall, nut inside.
   Optional two M3 into the holes 6 mm above the pivot. The flat face of the sector goes against the wall;
   the engraved angle numbers face out.
5. **Lid** on with "FRONT" toward the engraved wall; two M3 into the corner posts if you have them.
6. **Arm** on the rail: the bar sits in the V-groove across the foot, one zip tie through each row of
   slots and over the bar. Or two M4 bolts down through the slots into a roof, shelf or table edge (the
   diorama). Pull the pin, tilt, push the pin into the nearest hole.

## Tilt settings

Angle = tray face from straight down (0°). Steps of 15° to 90°. See `aim-coverage.png` for the geometry;
tilting swings the camera's narrow 48.8° axis because the module's 25 mm edge lies along the pivot axis.

| Setting | Use | Sees (camera face 60 cm over the pit) |
|---|---|---|
| **0°** | straight down; the default field setting for a tree pit | 54 × 72 cm patch centred under the node |
| **15–30°** | bias the patch toward the far side of the pit without losing the near side | floor from −10 to +49 cm (15°), +6 to +84 cm (30°) |
| **45°** | look across the pit at the run along the far rail | floor from 23 cm out to a far rail 127 cm away, plus ~12 cm up its post (160 cm on open ground) |
| 60–90° | horizontal-ish; a wall or a burrow mouth, not a pit | |

For the **diorama** (faceplate 25 cm over the floor): **0°** frames 23 × 30 cm of floor, all of it in
focus, good for the "live trigger" demo where the prop crosses under the node. **45°** shows the floor from
9 cm out to a wall 35 cm away plus 12 cm of that wall; use it if the prop runs along the back wall or if
you want the wall in shot for context. For a **real rail**, start at 0° and go to 45° only when the rat
run is along the far side of the guard; beyond 45° the near half of the pit leaves the frame and the IR
board lights the far rail more than the ground.

Rough print times (0.28 mm): tray 25 min, body 1.5 h, lid 35 min, sector + arm 30 min.
