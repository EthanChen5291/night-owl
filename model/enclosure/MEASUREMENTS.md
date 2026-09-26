# Enclosure measurement sheet

Every number below was read from the live OpenSCAD sources in `~/div-hacks-26/enclosure/` (branch
`enclosure-v2`, not pushed) on 2026-09-26. Derived values were recomputed by hand and cross-checked
against OpenSCAD 2026.09.23's `echo()` output and the bounding boxes of the exported STLs. The SCAD,
STL, shell and preview files stay in Bruno's repo; nothing here is a copy of them.

Conventions: mm unless stated. `file:line` is the line the value is defined on. Axes for D3 / owl / v2:
x = front (0) → rear (USB/Ethernet end), y = port side (0) → arm/battery side, z = up. For D3 and owl
z = 0 is the outer sensor face of the tray.

**Flagged values** (README §4 and §6, and the SCAD comments): the IR board `led_board`, `led_lens_d`,
`led_lens_off` are **UNMEASURED** guesses; measure the real 850 nm board before printing the tray.

---

## 1. D3 (`node_d3.scad` + `hanger.scad`) — the print-ready design

### 1.1 Top-level switches

| Variable | Value | Meaning | Source |
|---|---|---|---|
| `part` | `"all"` | what to render; see HANDOFF-D3 | node_d3.scad:16 |
| `power` | `"usb"` | `"usb"` = no battery inside, `"pisugar"` = 5000 mAh pack under the stack | node_d3.scad:17 |
| `tilt_preview` | 30 ° | angle shown in the `assembled` preview only | node_d3.scad:18 |
| `$fn` | 48 | circle resolution | node_d3.scad:76 |

### 1.2 Measured hardware (inputs)

| Item | Variable | Value | Note | Source |
|---|---|---|---|---|
| Pi 5 board | `pi_len` × `pi_wid` | 85 × 56 | | node_d3.scad:21 |
| Pi 5 hole spacing | `hole_dx` × `hole_dy` | 58 × 49 | official drawing | node_d3.scad:22 |
| Pi 5 hole inset | `hole_inset` | 3.5 | from the microSD end and both long edges | node_d3.scad:22 |
| Stack height | `stack_top` | 24 | PiSugar studs → top of the GPIO wire plugs (measured) | node_d3.scad:23 |
| Wire bend room | `wire_bend` | 5 | (v2 used 8) | node_d3.scad:24 |
| PiSugar stud socket | `stud_d` | 6.4 | M2.5 hex standoff is 5.8 across corners | node_d3.scad:25 |
| Stud socket depth | `stud_socket` | 3 | | node_d3.scad:25 |
| Camera board | `cam_board` | [25, 24] | Arducam IMX219; the 25 mm edge (ribbon edge) lies along **y** | node_d3.scad:27 |
| Camera hole | `cam_hole` | 12.5 dia, round | 8.5 mm square lens holder, diagonal 12.0 | node_d3.scad:28 |
| **IR board** | `led_board` | [21, 29] | w along y × l along x. **UNMEASURED** | node_d3.scad:31 |
| **IR lens hole** | `led_lens_d` | 10 | **UNMEASURED**; v2 used a 19 mm barrel (see §5) | node_d3.scad:32 |
| **IR lens offset** | `led_lens_off` | [0, 0] | lens centre vs board centre; **UNMEASURED** | node_d3.scad:33 |
| PIR board | `pir_board` | [32, 24] | HC-SR501 | node_d3.scad:35 |
| PIR dome | `pir_dome_d` | 23.5 | | node_d3.scad:35 |
| PiSugar 5000 mAh pack | `batt` | [67, 55, 12] | model 955564, measured with label | node_d3.scad:36 |
| Battery play | `batt_clear` | 3 | | node_d3.scad:36 |

Ghost hardware used by the fit check (`parts()`, node_d3.scad:179–205), all as boxes placed relative to
the Pi origin `(pi_x0, pi_y0, z0)` with `z0 = deck_z + deck_t + 1 + stud_socket` (= 20.8 usb) or `+ lift`
(pisugar): PiSugar board 85 × 56 × 1.6 at z0; Pi board 85 × 56 × 1.6 at z0 + 9; heatsink 48 × 40 × 7 at
z0 + 10.6; fan 30 × 30 × 1.5 at z0 + 17.6; two USB stacks 17 × 13 × 16 and Ethernet 21 × 16 × 14 hanging
3 / 2 mm past the rear edge; GPIO header 51 × 5 × 9; wire plugs 8 × 5 up to `stack_top`; USB-C 9 × 5 × 3.5,
2× micro-HDMI 7 × 5 × 3.5 and CAM0 5 × 3 × 3 on the port edge. Sensors: camera board 24 × 25 × 1 flat on
the tray, 8.5 mm square lens holder reaching 4 mm below the face, 12 × 6 × 3 ribbon connector, 12 × 11 ×
0.3 ribbon heading for the deck slot; IR board 29 × 21 × 1.6 with a `led_lens_d − 1` = 9 mm cylinder
poking 3 mm below the face; PIR board 24 × 32 × 1.6, hemispherical dome, 12 × 24 × 9 pin/plug block.

### 1.3 Case parameters

| Variable | Value | Meaning | Source |
|---|---|---|---|
| `chamfer` | 5 | 45° cut on the four vertical edges | node_d3.scad:39 |
| `wall` | 1.6 | body side walls | node_d3.scad:40 |
| `deck_t` | 1.6 | body floor (deck) the Pi sits on | node_d3.scad:41 |
| `lid_t` | 1.0 | clear PETG lid top | node_d3.scad:42 |
| `tray_t` | 1.2 | frosted PETG faceplate; also the tray/lid skirt thickness | node_d3.scad:43 |
| `skirt` | 6 | how far the lid and tray skirts overlap the body wall | node_d3.scad:44 |
| `fit` | 0.2 | clearance between a skirt and the body wall, per side | node_d3.scad:45 |
| `clear` | 1.5 | gap around the Pi | node_d3.scad:46 |
| `rear_clear` | 2 | extra gap at both ends so the Pi's corners clear the chamfers | node_d3.scad:47 |
| `sensor_depth` | 14 | tray inside height above the faceplate | node_d3.scad:48 |
| `gap` | 3 | between the three sensor boards | node_d3.scad:49 |
| `edge` | 6 | sensor row margin to the tray walls | node_d3.scad:49 |

### 1.4 Derived dimensions (recomputed; `echo` at node_d3.scad:77 prints "95.2 x 99.2 x 48.8 mm; band 21.2 mm")

| Quantity | Formula | usb | pisugar | Source |
|---|---|---|---|---|
| `lift` | battery thickness if internal | 0 | 12 | node_d3.scad:52 |
| `inner_h` | 1 + lift + stack_top + wire_bend + 1 | 31 | 43 | node_d3.scad:53 |
| `row_w` | edge + 21 + gap + 25 + gap + 32 + edge | 96 | 96 | node_d3.scad:55 |
| `inner_w` | max(row_w, pi_wid + 2·clear + 20 = 79) | 96 | 96 | node_d3.scad:56 |
| `inner_l` | pi_len + 2·clear + 2·rear_clear | 92 | 92 | node_d3.scad:57 |
| **`ext_l`** (body) | inner_l + 2·wall | **95.2** | 95.2 | node_d3.scad:58 |
| **`ext_w`** (body) | inner_w + 2·wall | **99.2** | 99.2 | node_d3.scad:59 |
| `deck_z` | tray_t + sensor_depth (underside of the body) | 15.2 | 15.2 | node_d3.scad:60 |
| `body_h` | deck_t + inner_h | 32.6 | 44.6 | node_d3.scad:61 |
| `top_z` | deck_z + body_h (lid underside) | 47.8 | 59.8 | node_d3.scad:62 |
| **`ext_h`** | top_z + lid_t | **48.8** | 60.8 | node_d3.scad:63 |
| **band** (tray skirt height) | deck_z + skirt | **21.2** | 21.2 | node_d3.scad:77, 158 |
| Tray/lid outer footprint | ext_l + 2·(tray_t + fit) × ext_w + 2·(tray_t + fit) | **98.0 × 102.0** | same | node_d3.scad:140, 157 |
| True envelope, no sector plate | | **98.0 × 102.0 × 48.8** | 98.0 × 102.0 × 60.8 | STL bbox |
| Envelope with sector plate | + `plate_t` = 4 on the arm side (y) | 98.0 × 106.0 × 48.8 | | hanger.scad:26 |

The README's "95 × 99 × 49" is the **body** outline; the tray and lid skirts sit 1.4 mm proud all round,
so the printed object measures 98.0 × 102.0 × 48.8 (confirmed by the `d3_tray.stl` / `d3_lid.stl`
bounding boxes: x −1.4…96.6, y −1.4…100.6). The README's "12 mm band" does not appear anywhere in the
CAD: the frosted skirt is 21.2 mm tall (1.2 faceplate + 14 sensor zone + 6 overlap).

### 1.5 Positions inside the box (usb variant; pisugar shifts z-values by +12 where `lift` appears)

| Feature | Value | Source |
|---|---|---|
| Sensor row centre `row_x` | ext_l / 2 = 47.6 | node_d3.scad:68 |
| IR centre `led_y` | wall + edge + 21/2 = 18.1 | node_d3.scad:65 |
| Camera centre `cam_y` | 18.1 + 10.5 + 3 + 12.5 = 44.1 | node_d3.scad:66 |
| PIR centre `pir_y` | 44.1 + 12.5 + 3 + 16 = 75.6 | node_d3.scad:67 |
| Sensor order along y | IR (port side) → camera → PIR (arm side) | node_d3.scad:65–67 |
| Pi origin `pi_x0`, `pi_y0` | 5.1, 3.1 (wall + clear + rear_clear; wall + clear) | node_d3.scad:70–71 |
| Pi stud sockets (centres) | x = 8.6 and 66.6; y = 6.6 and 55.6; socket d 6.4 in a d 9.4 boss, 1 + 3 tall | node_d3.scad:128–132 |
| Pi stud sockets sit on | deck top, z = deck_z + deck_t = 16.8 | node_d3.scad:129 |
| Ghost Pi board top | z0 + 9 + 1.6 = 31.4; fan top 39.9; wire plugs top 44.8; lid underside 47.8 | node_d3.scad:180–189 |
| Pivot `pivot` | [ext_l/2, ext_w, ext_h/2] = [47.6, 99.2, 24.4] on the arm-side wall | node_d3.scad:72 |
| Pivot hole in the wall | d 4.4 (M4), through the arm-side wall at `pivot` | node_d3.scad:110 |
| Sector M3 holes in the wall | d 3.2, at pivot.x ± 10, pivot.z + 6 (= 30.4) | node_d3.scad:111 |
| `sector_zone()` notch (lid + tray skirts) | x 13.6…81.6 (2·pin_r + 16 = 68 wide), z 10.4…60.4 (pin_r + 24 = 50 tall), 10 deep from y = ext_w − 0.5 | node_d3.scad:93 |
| Port window (y = 0 wall) | x 6.1…76.1 (70 long), z 17.3…37.3 (20 tall); USB-C, 2× HDMI, PiSugar ports | node_d3.scad:96 |
| Rear opening (x = ext_l wall) | y 4.1…58.1 (54 wide), z 18.8…49.8 (31 tall); USB ×4 + Ethernet | node_d3.scad:97 |
| Deck cable slot | x 31.6…63.6 (32 long), y 23.1…30.1 (7 wide), through the deck; ribbon, PIR wires, IR lead | node_d3.scad:106 |
| Front-wall vents | 8 slots, 5 wide × 6 tall, y = 9.6 + 11·i, z 38.8…44.8 | node_d3.scad:108 |
| Lid posts | 2 × (10 × 10 mm, `inner_h` tall) at x = 0 and x = 85.2, y = 89.2; screw hole d 2.6 × 9 deep at (6.5, 3.5) and (3.5, 3.5) inside the post | node_d3.scad:119–122 |
| Lid M3 holes | d 3.2 at (6.5, 92.7) and (88.7, 92.7) | node_d3.scad:148 |
| Lid fan grille | 10 slots 3 wide × 44 long, x = 17.1 + 6·i, y 9.1…53.1 | node_d3.scad:146 |
| Lid skirt | 6 tall, outside the body, 1.2 thick (offset 1.4 outer, 0.2 inner) | node_d3.scad:140–143 |
| Tray pocket | offset(fit) around the body outline, z 1.2…15.2 | node_d3.scad:160 |
| Tray overlap zone | z 15.2…21.2, same offset | node_d3.scad:161 |
| Tray camera hole | d 12.5 at (47.6, 44.1) | node_d3.scad:163 |
| Tray PIR hole | d pir_dome_d + 0.5 = 24.0 at (47.6, 75.6) | node_d3.scad:164 |
| Tray IR hole | d 10 at (47.6 + off.x, 18.1 + off.y) | node_d3.scad:165 |
| Tray IR-lead notch (rear) | x 90.2…100.2, y 65.6…75.6, z 9.2…29.2 | node_d3.scad:167 |
| Board fences `frame()` | 2 tall, 1.2 thick, 0.3 clearance per side around the board; camera fence open on the −y side over `b[0] − 4` = 20 mm for the ribbon | node_d3.scad:85–91, 171–175 |
| Fence pockets | camera 24 × 25 (x × y), PIR 24 × 32, IR 29 × 21, each + 0.6 | node_d3.scad:172–174 |
| Labels | "PI 5 · PORTS THIS SIDE" and "ARM SIDE" engraved 0.6 into the deck; "SB-01" 0.6 into the front wall; "FRONT" 0.4 into the lid | node_d3.scad:113–116, 149 |
| PiSugar variant fences | 1.6 thick, lift + 5 = 17 tall, in front of and beside the stack; no stud sockets | node_d3.scad:123–126 |
| Camera ribbon | 12 cm long; tray → deck slot → CAM0 path ≈ 7 cm (HANDOFF-D3 in Bruno's repo) | HANDOFF-D3.md:82 |

### 1.6 Hanger (`hanger.scad`): sector, arm, pin

| Variable | Value | Meaning | Source |
|---|---|---|---|
| `box` | [109, 104, 45] | box size used **only** by hanger.scad's own `assembled()` preview; it is the v2 size, not D3 | hanger.scad:17 |
| `pivot_z` | 22.5 | same preview only | hanger.scad:18 |
| `angles` | [0, 15, 30, 45, 60, 75, 90] | 7 pin holes; D3: 0 = straight down, 90 = face forward | hanger.scad:21–22 |
| `pivot_d` | 4.4 | M4 pivot bolt hole (sector, arm and box wall) | hanger.scad:23 |
| `pin_d` | 4.4 | index pin hole; M4 bolt, nail or 4 mm hex key | hanger.scad:24 |
| `pin_r` | 26 | pin circle radius; holes 6.8 apart at 15°, 2.4 web between | hanger.scad:25 |
| `plate_t` | 4 | sector thickness = pin engagement | hanger.scad:26 |
| `arm_t` | 6 | arm bar thickness | hanger.scad:27 |
| `arm_w` | 20 | arm bar width | hanger.scad:28 |
| `drop` | 65 | pivot centre below the foot's underside | hanger.scad:29 |
| `foot_l` | 46 | foot length across the bar | hanger.scad:30 |
| `foot_w` | 22 | foot width along the bar | hanger.scad:31 |
| `foot_t` | 8 | foot thickness | hanger.scad:32 |
| `slot` | [7, 4.5] | zip-tie slots (an M4 bolt fits too) | hanger.scad:33 |
| `$fn` | 40 | | hanger.scad:35 |

Derived hanger geometry:

| Feature | Value | Source |
|---|---|---|
| Sector outline | half-disc of radius pin_r + 6 = 32 (y ≥ 0), plus a 28 × 13 tab under the pivot (y −12…1); 4 thick; STL bbox 64 × 44 × 4 | hanger.scad:40–44 |
| Pin holes | 7 × d 4.4 on r = 26 at angle 90° − a from +x (a = 0 straight up, a = 90 along +x) | hanger.scad:47 |
| Pin hole pitch / web | 2·26·sin 7.5° = 6.79 / 6.79 − 4.4 = 2.39 | hanger.scad:25 |
| Sector M3 holes | d 3.2 at (±10, 6), matching node_d3.scad:111 | hanger.scad:48 |
| Angle labels | "0"…"90" engraved 0.5 deep at r = 30.2, text size 2.6 | hanger.scad:49–50 |
| Arm leg | hull of a 20 × 6 × 1 block at the foot down to an r = 10 disc at z = −65; pivot hole d 4.4 at (10, −65) | hanger.scad:57–60, 64 |
| Arm pin hole | d 4.4 at z = −drop + pin_r = −39 (straight above the pivot = angle 0) | hanger.scad:65 |
| Arm foot | 46 × 22 × 8, spanning x −13…33 | hanger.scad:61 |
| V-groove | along the bar (y), 3.5 deep, 7 wide at the surface, 90° included angle (rotated 7√2 square) | hanger.scad:67 |
| Zip-tie / bolt slots | 4 × (7 × 4.5) through the foot at x −10…−3 and 23…30, y 4…8.5 and 13.5…18 | hanger.scad:70–71 |
| Arm overall (STL bbox) | 46 × 83 × 22 as exported (printed lying on its flat face) | stl/hanger_arm.stl |
| Printed pin | head d 10 × 4 long, shank d pin_d − 0.4 = 4.0 × (arm_t + plate_t + 1) = 11 long; STL 15 × 10 × 10 | hanger.scad:76 |
| Box corner swing (D3) | √(47.6² + 24.4²) = 53.5 from the pivot → 11.5 clearance under a 65 drop. hanger.scad:29's "59 mm" is the v2 box | hanger.scad:29 |
| Sector position on D3 at tilt 0 | pin at z = 24.4 + 26 = 50.4 (1.6 above the lid top), plate top at z = 56.4 | node_d3.scad:72, hanger.scad:25 |
| Range | 0…90° in 15° steps, one pin | hanger.scad:21 |

Fastener summary for D3: pivot M4 × 30 + nut (through arm 6 + sector 4 + wall 1.6 + nut); pin = M4 bolt /
nail / 4 mm hex key or the printed pin; 2× M3 × 8 sector → wall (d 3.2 clearance, optional); 2× M3 × 8
lid → posts (d 2.6 self-tap in the posts, d 3.2 clearance in the lid, optional); 2 zip ties (7 × 4.5
slots); hot glue for the boards.

### 1.7 Tolerances and clearances (D3)

| Where | Value | Source |
|---|---|---|
| Skirt ↔ body wall | 0.2 per side (`fit`) | node_d3.scad:45 |
| Board ↔ fence pocket | 0.3 per side | node_d3.scad:87–88 |
| Pi ↔ cavity, sides | 1.5 (`clear`); ends 1.5 + 2 (`rear_clear`) | node_d3.scad:46–47 |
| Pi ↔ battery-side wall | inner_w − (pi_y0 − wall) − pi_wid = 96 − 1.5 − 56 = 38.5 (the cable bay) | derived |
| Stack top ↔ lid underside | wire_bend + 1 = 6 nominal (from the stud tips); the ghost stack, measured from the PiSugar board, leaves 3 (plugs top 44.8 vs lid 47.8) | node_d3.scad:53, 180, 189 |
| Above the boards in the tray | sensor_depth − 1.6 (board) − 9 (PIR plugs) = 3.4 | node_d3.scad:48, 204 |
| PIR dome hole ↔ dome | 0.5 on the diameter | node_d3.scad:164 |
| Camera hole ↔ holder diagonal | 12.5 − 12.0 = 0.5 | node_d3.scad:28 |
| Battery ↔ fences | 3 (`batt_clear`) | node_d3.scad:36 |
| M4 hole vs bolt | 4.4 vs 4.0 | hanger.scad:23 |
| Printed pin vs hole | 4.0 vs 4.4 | hanger.scad:76 |

---

## 2. Owl variant (`node_owl.scad`, untracked, previews only)

Same file as D3 with these differences. Everything not listed is identical (same variable names, lines
shifted by about +4 to +8).

| Variable | Owl | D3 | Meaning | Source |
|---|---|---|---|---|
| `corner_r` | 9 | — | rounded vertical edges replace the 5 mm chamfer (`chamfer` is declared but unused) | node_owl.scad:43–44 |
| `outline()` / `oc()` | `offset(r)` rounded rectangle | 45° polygon | | node_owl.scad:90–91 |
| `face_w` | 88 | — | heart width across the sensor row | node_owl.scad:45 |
| `face_tip` | 6 | — | heart tip, mm from the front wall | node_owl.scad:46 |
| `face_recess` | 0.8 | — | depth of the facial-disc recess in the tray face | node_owl.scad:47 |
| `tray_t` | **2.0** | 1.2 | thicker faceplate so the 0.8 recess leaves 1.2 | node_owl.scad:51 |
| `deck_z` | 16.0 | 15.2 | tray_t + sensor_depth | node_owl.scad:68 |
| `top_z` / `ext_h` | 48.6 / **49.6** | 47.8 / 48.8 | | node_owl.scad:70–71 |
| band | **22.0** | 21.2 | deck_z + skirt | node_owl.scad:85 |
| tray/lid footprint | **99.6 × 103.6** | 98.0 × 102.0 | ext + 2·(tray_t + fit) | node_owl.scad:156, 173 |
| tray/lid skirt thickness | 2.0 | 1.2 | tray_t + fit − fit | node_owl.scad:173–176 |
| Heart (`heart2d`) | two r = 22 lobes at (53.6, 27.6) and (53.6, 71.6) hulled to an r = 1.5 tip at (7.5, 49.6), plus an r = 14 cleft disc at (45.6, 49.6) so the camera hole sits inside the disc | | node_owl.scad:108–112, 178 |
| Vents | 12 "feather-comb" slots on the front wall, 2.2 wide, length 5 + 5·sin(180·i/11) (5…10), y = 10.6 + 7·i, tilted 25° | 8 straight slots | node_owl.scad:123–124 |
| Front label | "OWL-01" | "SB-01" | node_owl.scad:132 |
| Extra `part` | `"face"` (tray + body + parts, tray 85 % opaque) | — | node_owl.scad:245 |

x/y hardware positions (`led_y`, `cam_y`, `pir_y`, `row_x`, `pi_x0`, `pi_y0`, stud sockets, openings)
are identical to D3; z positions above the face shift by +0.8 because `deck_z` moved. No STLs exist;
`build_d3.sh` does not reference this file.

---

## 3. v2 (`node_v2.scad`) — printed once, leave alone

### 3.1 Inputs

| Item | Variable | Value | Source |
|---|---|---|---|
| Switches | `part`, `power` | `"all"`, `"usb"` | node_v2.scad:19, 23 |
| Pi 5 | `pi_len` × `pi_wid`, `hole_dx` × `hole_dy`, `hole_inset` | 85 × 56, 58 × 49, 3.5 | node_v2.scad:27–31 |
| Stack | `stack_top`, `wire_bend`, `stud_d`, `stud_socket` | 24, 8, 6.4, 3 | node_v2.scad:32–35 |
| Camera | `cam_board`, `cam_holder` | [25, 24], 10.5 square hole | node_v2.scad:38–39 |
| IR board | `led_board`, `led_lens_d` | [21, 29] (29 incl. wire exit), **19 lens barrel** — unmeasured | node_v2.scad:44–45 |
| PIR | `pir_board`, `pir_dome_d` | [32, 24], 23.5 | node_v2.scad:48–49 |
| Battery | `batt`, `batt_clear` | [67, 55, 12], 3 | node_v2.scad:52–53 |
| Stand | `tilt`, `stand_h0` | 20 °, 5 | node_v2.scad:56–57 |
| Case | `chamfer`, `wall`, `floor_t`, `clear`, `sensor_depth`, `gap`, `edge`, `rear_clear` | 5, 2.4, 2.4, 1.5, 16, 3, 6, 2 | node_v2.scad:60–68 |
| Lid | `lid_t`, `lip`, `lip_w`, `fit` | 2.4, 5, 2, 0.3 | node_v2.scad:69–72 |

### 3.2 Derived (`echo` at node_v2.scad:100 → "109.3 x 103.8 x 44.8 mm" usb, "… x 56.8" pisugar)

| Quantity | Formula | usb | pisugar | Source |
|---|---|---|---|---|
| `inner_h` | 1 + lift + 24 + 8 + 7 | 40 | 52 | node_v2.scad:76 |
| `sensor_z` | floor_t + 19 | 21.4 | 21.4 | node_v2.scad:77 |
| `row_w` | 6 + 22 + 3 + 26 + 3 + 33 + 6 | 99 | 99 | node_v2.scad:79 |
| `inner_w` | max(99, 79) | 99 | 99 | node_v2.scad:80 |
| `inner_l` | 16 + 85 + 1.5 + 2 | 104.5 | 104.5 | node_v2.scad:81 |
| `chamfer_in` | 5 − 2.4·(2 − √2) | 3.59 | 3.59 | node_v2.scad:82 |
| **`ext_l` × `ext_w`** | inner + 2·2.4 | **109.3 × 103.8** | same | node_v2.scad:83–84 |
| `ext_h` (base) | floor_t + inner_h | 42.4 | 54.4 | node_v2.scad:85 |
| **height with lid** | ext_h + lid_t | **44.8** | **56.8** | node_v2.scad:100 |
| Base STL bbox (x) | hood 5 + collar 3 protrude at the front | 114.3 × 103.8 × 42.4 | 114.3 × 103.8 × 54.4 | stl/v2_base_*.stl |
| `led_y`, `cam_y`, `pir_y` | | 19.4, 46.4, 78.9 | | node_v2.scad:88–90 |
| `pi_x0`, `pi_y0`, `pcb_z` | | 18.4, 3.9, 10.9 | | node_v2.scad:93–95 |

The README (and V2_NOTES.md in Bruno's repo) say 107 × 96 × 45 / 57. The current file gives 109.3 ×
103.8 × 44.8 / 56.8; the 107 × 96 figure predates the "review fixes" commit (5296e73: chamfers, wider
grille, `rear_clear`). `hanger.scad:17`'s `box = [109, 104, 45]` matches the current v2.

### 3.3 v2 features

| Feature | Value | Source |
|---|---|---|
| Front holes | IR: d led_lens_d + 0.8 = 19.8 round; camera: 10.5 square; PIR: d 23.5 round; all centred at z = 21.4 | node_v2.scad:128–130 |
| Rear opening | y 4.9…58.9 (54 wide), z 4.4…35.4 (31 tall) | node_v2.scad:133 |
| Rear cable-bay notch (IR lead) | y 66.4…80.4 (14), z 4.4…18.4 (14) | node_v2.scad:136 |
| Port-side window | x 19.4…89.4 (70), z 2.9…22.9 (20) | node_v2.scad:140 |
| Battery-side vents | 8 × (4 wide × 8 tall), x = 26.4 + 10·i, z 30.4…38.4 | node_v2.scad:143–144 |
| Sensor rails | 1.6 thick, board width + 0.8 apart; depth 5 / 7 / 5 and height 24 / 20 / 26 for IR / PIR / camera | node_v2.scad:107–111, 174–176 |
| Camera hood | 5 long, 15 × 15 opening, 45° taper underneath | node_v2.scad:180–187 |
| PIR collar | cone 3 tall, d 34 → 28 outside, d 24 inside | node_v2.scad:188–191 |
| Stud sockets / battery tray / fences | as D3 (sockets d 6.4 in d 9.4, 1 + 3 tall); tray 73 × 61 × 1.5 with 1.6 walls; fences 1.6 × (lift + 5) | node_v2.scad:151–170 |
| Lid | 2.4 top, lip 5 deep × 2 wide, 0.3 clearance; grille 12 × (3 × 48) at x = 26.4 + 6·i, y 7.9…55.9; "FRONT" label | node_v2.scad:195–208 |
| PIR shroud | 30 long, OD 32, ID 28.4 (slides over the collar) | node_v2.scad:211–216 |
| IR diffuser (clear PETG) | 14.8 tall, OD 22.4, ID 19.8, 0.8 floor | node_v2.scad:218–223 |
| Stand | 20° wedge, 5 tall at the front lip; footprint (ext_l + 6) × (ext_w + 6) = 115.3 × 109.8; rails 12 wide; lip 3 thick × 5 tall; camera ends up ≈ 26 mm above the table | node_v2.scad:232–247 |
| Test plate | the front wall only (x ≤ wall + 8) | node_v2.scad:249–254 |
| Labels | "PI 5 · PORTS THIS SIDE", "CABLES" in the floor; "FRONT" in the lid | node_v2.scad:147–148, 206 |

---

## 4. v1 (`enclosure.scad`, `build_stl.py`) — superseded, for the record

Plain rectangular tray + lid with the camera and PIR on the lid. `wall` 2.4, `floor_t` 2.4, `clear` 1.5,
`pisugar_h` 15 (flagged "MEASURE YOURS"), `pi_comp_h` 20 (22 in build_stl.py), `screw_d` 2.5 self-tap
M2.5, `cam_lens_hole` 9, camera mount holes 21 × 12.5 at d 2.2, `pir_dome_d` 23.5, `lid_lip` 6 (5.0 in
build_stl.py). enclosure.scad:19–51, build_stl.py:12–19. Its STLs (`base_no_pisugar.stl`,
`base_with_pisugar.stl`, `lid.stl`) are the 2026-09-24 23:35 trimesh exports.

---

## 5. Flags and contradictions found while measuring

1. **IR board unmeasured** (README §4, §6; node_d3.scad:30 "CHECK THESE AGAINST THE REAL BOARD").
   `led_board` [21, 29], `led_lens_d` 10, `led_lens_off` [0, 0]. Note that **v2 drew the same board with a
   19 mm lens barrel** (node_v2.scad:45, "black cylindrical lens") while D3 cuts a **10 mm** hole for "the
   LED lens". One of the two is wrong for the real part; if the barrel really is ~19 mm the D3 tray hole
   must grow and the IR fence (29 × 21) may need to move. This is the tray-first test print's job.
2. **Outer size**: README "95 × 99 × 49" is the body; the print envelope is 98.0 × 102.0 × 48.8 (skirts
   proud by 1.4), 106 wide with the 4 mm sector plate.
3. **Band height**: README/plan say "lower 12 mm frosted band"; the CAD's band is **21.2 mm** (22.0 owl).
4. **v2 size**: README/V2_NOTES "107 × 96 × 45" vs the file's 109.3 × 103.8 × 44.8 (114.3 long with the
   hood and collar).
5. **Fit check**: `fit_body` and `fit_lid` render as "Current top level object is empty"; `fit_tray` and
   `fitcheck` do **not** — with OpenSCAD 2026.09.23 they export a 68-facet sheet of **zero volume** lying
   entirely in the plane z = 1.2 (the ghost boards' undersides coincide with the tray face). The
   "0 mm³ overlap" claim holds; the "grep for empty" recipe in Bruno's HANDOFF-D3.md does not, for the tray.
6. `hanger.scad:29` says the box corner swings 59 mm from the pivot; that is the v2 box. For D3 it is
   53.5 mm (11.5 mm under the foot).
7. Bruno's HANDOFF-D3.md refers to a `groove` variable in hanger.scad ("seats 12–25 mm"). No such variable
   exists; the V-groove is hard-coded at hanger.scad:67 (3.5 deep, 7 wide at the surface, 90°). A round
   bar of any diameter ≥ 7 mm rests on the two flanks; the zip ties do the holding.
8. Camera FOV: Bruno's HANDOFF-D3.md says 62° × 49°; the IMX219 datasheet says 62.2° × 48.8°. The camera's
   25 mm edge lies along y, which is the hanger's tilt axis, so the **48.8° axis is the one that sweeps**
   when you tilt. See `aim_coverage.py` for the consequences (README's 67 × 50 and 127 cm do not
   reproduce exactly from the datasheet FOV; 72 × 54 and "reaches a far rail at 127 cm, 12 cm up its
   post" do).
9. hanger.scad:16–17 comment "from node_v2 / D3" for `box`: it is v2 only and affects only hanger.scad's
   own preview; node_d3.scad's `hung()` uses its own `pivot`.

---

## 6. Files present in `~/div-hacks-26/enclosure/` (listing only, not copied)

Sources: `node_d3.scad` (14,463 B, 09-25 15:20), `hanger.scad` (5,538 B, 09-25 15:20), `node_v2.scad`
(16,711 B, 09-25 01:16), `node_owl.scad` (15,836 B, 09-25 21:59, **untracked**), `enclosure.scad` (v1,
09-24 23:35), `build_d3.sh` (09-25 15:20), `build_v2.sh` (09-25 00:01), `build_stl.py` (v1, 09-24 23:35),
`D3_NOTES.md` (09-25 15:21), `HANDOFF-D3.md` (09-25 15:34), `V2_NOTES.md` (09-25 00:01).

`stl/` (all 2026-09-25 unless noted):

| File | Size | Time | Bbox (mm) |
|---|---|---|---|
| `d3_body.stl` | 2,893,815 | 15:20:56 | 95.2 × 99.2 × 32.6 |
| `d3_lid.stl` | 366,973 | 15:20:56 | 98.0 × 102.0 × 7.0 |
| `d3_tray.stl` | 192,452 | 15:20:56 | 98.0 × 102.0 × 21.2 |
| `d3_fitcheck.stl` | 13,540 | 15:20:56 | zero-volume sheet at z = 1.2 |
| `d3_fit_tray.stl` | 13,540 | 15:20:58 | same |
| `hanger_arm.stl` | 104,715 | 15:20:56 | 46 × 83 × 22 |
| `hanger_sector.stl` | 1,342,848 | 15:20:56 | 64 × 44 × 4 |
| `hanger_pin.stl` | 72,979 | 15:20:56 | 15 × 10 × 10 |
| `v2_base_usb.stl` | 2,318,863 | 15:16:19 | 114.3 × 103.8 × 42.4 |
| `v2_base_pisugar.stl` | 1,948,233 | 15:16:20 | 114.3 × 103.8 × 54.4 |
| `v2_lid.stl` | 278,713 | 15:16:20 | 109.3 × 103.8 × 7.4 |
| `v2_stand.stl` | 8,469 | 15:16:20 | 115.3 × 109.8 × 47.0 |
| `v2_pir_shroud.stl` | 86,763 | 15:16:20 | |
| `v2_led_diffuser.stl` | 87,261 | 15:16:20 | |
| `v2_test_plate.stl` | 213,071 | 15:16:20 | |
| `base_no_pisugar.stl`, `base_with_pisugar.stl`, `lid.stl` (v1) | 110,684 / 111,084 / 80,284 | 09-24 23:35 | |

`preview/`: `d3_assembled.png`, `d3_cutaway.png`, `d3_inside.png`, `d3_parts.png`, `d3_underside.png`
(09-25 15:20); `hanger_assembled.png`, `hanger_parts.png` (09-25 15:04); `owl_assembled.png`,
`owl_face.png`, `owl_face_angle.png`, `owl_parts.png`, `owl_tray.png`, `owl_underside.png` (09-25 21:59–22:00,
**untracked**); `v2_cutaway.png`, `v2_front.png`, `v2_front_flat.png`, `v2_front_pisugar.png`,
`v2_inside.png`, `v2_inside_parts.png`, `v2_inside_parts_pisugar.png`, `v2_inside_pisugar.png`,
`v2_on_stand.png`, `v2_rear.png`, `v2_top.png`, `v2_xray.png` (09-25 01:07–15:16).

Git: branch `enclosure-v2`, last enclosure commit `57d77a2 Enclosure D3: face-down band box, indexed
hanger, handoff`; untracked: `node_owl.scad`, `preview/owl_*.png`, `.DS_Store`.
