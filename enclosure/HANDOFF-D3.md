# How the D3 CAD works

Sources: `~/div-hacks-26/enclosure/node_d3.scad`, `hanger.scad`, `build_d3.sh` (branch `enclosure-v2`,
local only). This file explains the model so you can change it without reverse-engineering it. Numbers
are in `MEASUREMENTS.md`; print and assembly are in `D3_NOTES.md`. Needs OpenSCAD 2025+ on PATH
(`/opt/homebrew/bin/openscad`, currently 2026.09.23).

## One idea

The box is a stack of three shells that all share one 2D outline. `outline(l, w, c)` is a rectangle with
45° corner cuts; `oc(d)` is that outline at the body's outer size, grown or shrunk by `d`. The body is
`oc(0)` outside and `oc(-wall)` inside; the tray and lid are `oc(tray_t + fit)` outside and `oc(fit)`
inside, so they slide over the body wall with `fit` (0.2 mm) of play. Nothing overhangs: the body prints
deck-down, the lid top-down, the tray face-down, and the two skirts sit **outside** the body wall.

Everything is derived from the hardware block at the top of the file. Change `pi_len` or `led_board` and
the outline, sensor positions, openings and previews all move. Do not edit the STLs.

## Coordinate frame

x runs front (0) → rear; the USB/Ethernet end of the Pi is at the rear. y runs port side (0) → arm side;
the Pi's USB-C/HDMI edge faces y = 0 and the hanger bolts to the y = `ext_w` wall. z is up with z = 0 at
the outer face of the tray, i.e. the face that looks at the ground when the node hangs.

Vertical stack (usb variant): tray 0 → 21.2 (faceplate 1.2, sensor zone to 15.2, 6 mm overlap), body
15.2 → 47.8 (deck 1.6 thick, walls 1.6), lid 41.8 → 48.8 (6 mm skirt, 1.0 mm top).

## What each parameter drives

| Parameter | Drives |
|---|---|
| `pi_len`, `pi_wid`, `clear`, `rear_clear`, `wall` | `inner_l`, `ext_l`; the stud-socket positions via `pi_x0`, `pi_y0` |
| `led_board[0]`, `cam_board[0]`, `pir_board[0]`, `gap`, `edge` | `row_w`, hence `inner_w`/`ext_w` (the row is wider than the Pi, so the sensors set the width) and `led_y`, `cam_y`, `pir_y` |
| `stack_top`, `wire_bend`, `lift` | `inner_h` → `body_h`, `top_z`, `ext_h`; also the z of the port window and rear opening |
| `sensor_depth`, `tray_t` | `deck_z` (where the body sits on the tray) and the band height `deck_z + skirt` |
| `skirt`, `fit` | how deep the tray and lid grip the body and how tight |
| `cam_hole`, `led_lens_d`, `led_lens_off`, `pir_dome_d` | the three holes in the faceplate |
| `led_board`, `cam_board`, `pir_board` | the fence pockets (`frame()`), each 0.3 mm looser per side, 2 mm tall |
| `pivot` = [ext_l/2, ext_w, ext_h/2] | the M4 hole, the two M3 holes 6 mm above it, `sector_zone()` and where `hung()` rotates |
| `hanger_dims()` from hanger.scad | `[drop, pin_r, plate_t, arm_t, arm_w]`; used for `sector_zone()` and to place the arm in the preview |
| `power` | `"pisugar"` adds 12 mm (`lift`) of height, replaces the stud sockets with two fences, and raises the openings |

Two things are not derived: the deck cable slot (32 × 7, node_d3.scad:106) is placed by hand relative to
`row_x` and `cam_y`, and the lid posts are fixed 10 × 10 blocks in the two arm-side corners (the Pi's corners
occupy the port-side ones).

## Modules

- `body()` — the black PLA shell. Difference of the outer extrusion and the cavity, minus the port window,
  rear opening, deck slot, eight front vents, the pivot/M3 holes and three engraved labels; then union the
  two lid posts and either the four stud sockets (usb) or the battery fences (pisugar).
- `lid()` — 1.0 mm clear top plus 6 mm skirt, minus the rear opening and `sector_zone()` (so it clears the
  sector plate), the 10-slot fan grille and the two M3 holes.
- `tray()` — faceplate plus 21.2 mm skirt, pocketed to `oc(fit)` from z = 1.2 up, minus the three sensor
  holes, the seam notches (`port_window()`, `rear_opening()`, the IR-lead notch, `sector_zone()`); then
  three `frame()` fences on the inside of the face. The camera fence is open on the −y side for the ribbon.
- `port_window()` and `rear_opening()` are shared by body and tray because they cross the tray/body seam.
- `parts()` — coloured ghost hardware (Pi 5, PiSugar, Active Cooler, USB/Ethernet stack, the three
  sensor boards with lens holder, IR lens and PIR dome). Used by the previews and by the fit check.
- `hung(a)` — the assembled preview: the arm placed by `hanger_dims()`, and body + lid + tray + sector +
  parts rotated `a` degrees about the pivot (`rotate([0, a, 0])`, i.e. about the y axis).
- In `hanger.scad`: `sector()` (index plate), `arm()` (L-bar with V-groove foot and slots), `pin()`, and
  `assembled()` (its own preview using the stale v2 `box`).

`part=` selects the output: `body`, `lid`, `tray` (print orientation: body shifted to z = 0, lid mirrored
top-down, tray as is), `assembled`, `inside`, `cutaway`, `xray`, `fitcheck`, `fit_body`, `fit_lid`,
`fit_tray`, `all` (a parts layout). In hanger.scad: `sector`, `arm` (rotated flat), `pin`, `assembled`, `all`.

## How tilt works, and how to change it

The body has no angled face. Tilt comes entirely from the hanger: the M4 pivot bolt passes through the arm
leg, the sector plate and the box wall at `pivot`. The sector is a half-disc (r = 32) with seven 4.4 mm
holes on a 26 mm circle at `angles` = 0, 15, …, 90°; the arm has one matching hole 26 mm straight above its
pivot hole. Pull the pin, swing the box so the hole you want lines up, push the pin back. 0° = tray face
straight down, 90° = face forward. (Angle labels are engraved beside each hole.)

- Different steps or range: edit `angles` in hanger.scad. Keep the spacing ≥ 15° at `pin_r` = 26, or the
  holes merge (2.4 mm web now); a finer index needs a larger `pin_r`, which also raises the plate above the
  lid.
- Preview a different angle: `tilt_preview` in node_d3.scad, or `openscad -D 'tilt_preview=45' -D
  'part="assembled"' node_d3.scad`.
- Move the pivot: `pivot` in node_d3.scad; the sector's M3 holes are at ±10, +6 from it in both files, so
  change both or the plate will not bolt on.
- Bigger bar or pole: the V-groove is hard-coded at hanger.scad:67 (3.5 deep, 7 wide); there is no `groove`
  variable despite what the older handoff says. Widen the rotated cube there, or rely on the zip ties.

## Exporting (`build_d3.sh`)

```sh
cd ~/div-hacks-26/enclosure && ./build_d3.sh
```

It runs OpenSCAD once per part with `-q -D 'part="…"'`: `stl/d3_body.stl`, `d3_lid.stl`, `d3_tray.stl` from
node_d3.scad; `stl/hanger_sector.stl`, `hanger_arm.stl`, `hanger_pin.stl` from hanger.scad; then
`stl/d3_fitcheck.stl` (must be empty, see below) and five previews with fixed `--camera` positions:
`preview/d3_assembled.png`, `d3_inside.png`, `d3_cutaway.png`, `d3_underside.png`, `d3_parts.png` at
1400 × 1000 (parts sheet 1600 × 1000), colour scheme Tomorrow. Everything takes about a minute. The
`power` variant is not looped: for the battery box add `-D 'power="pisugar"'` by hand. The owl variant is
not in the script at all.

One part by hand:

```sh
openscad -q -D 'part="tray"' -o stl/d3_tray.stl node_d3.scad
openscad -D 'part="assembled"' node_d3.scad        # opens the GUI on the hanging preview
```

## The fit check

`part="fitcheck"` intersects `parts()` with body + lid + tray; `fit_body`, `fit_lid`, `fit_tray` do one
shell each. Any plastic that would occupy the same space as a hardware ghost comes out as a solid. Re-run
after every change:

```sh
cd ~/div-hacks-26/enclosure
for p in fit_body fit_lid fit_tray; do openscad -D "part=\"$p\"" -o /tmp/$p.stl node_d3.scad 2>&1 | grep -i empty; done
```

What "empty" looks like today (OpenSCAD 2026.09.23): `fit_body` and `fit_lid` print "Current top level
object is empty." and write nothing useful; `fit_tray` (and `fitcheck`) write a 13.5 kB STL of 68 facets
that all lie in the plane z = 1.2, because the ghost boards sit exactly on the tray face. Its signed volume
is 0.0 mm³, which is the real criterion. If you want a robust check, compute the volume of the exported
STL (a 20-line Python loop over the facets, or `admesh`/`trimesh`) and require < 0.01 mm³ instead of
grepping for "empty". Anything with a z-range is a real collision.

The ghosts are boxes from datasheets plus a few measurements (`stack_top`, the battery, the PIR plug
block). The check proves clearances, not fit, and it cannot see the unmeasured IR board. That is why the
tray is printed first.

## Things to know before editing

- Keep `lid_t` at ~1.0–1.2 mm: the 2.4 mm PETG lid on v2 went opaque.
- Keep the lid posts in the arm-side corners; the Pi's corners sit in the port-side ones.
- The IR lead leaves through a notch in the tray's rear skirt (node_d3.scad:167), then out of the rear
  opening; the camera ribbon (12 cm, ~7 cm needed) and PIR wires go up through the deck slot.
- `hanger.scad`'s `box`, `pivot_z` and `assembled()` are for its own preview and still describe the v2 box;
  node_d3.scad ignores them and uses `hanger_dims()` only.
- `node_owl.scad` is a copy of node_d3.scad with rounded corners (`corner_r` 9), a 2.0 mm tray with a 0.8 mm
  heart recess and feather vents. Same hardware positions; not exported, not in `build_d3.sh`.
