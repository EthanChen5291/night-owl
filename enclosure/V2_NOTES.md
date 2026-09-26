# Enclosure v2 (side-facing box on a stand)

`~/div-hacks-26/enclosure/node_v2.scad`, `build_v2.sh`, `stl/v2_*.stl`, `preview/v2_*.png`. Built
2026-09-24, printed once, superseded by D3 on 09-25. **Leave it alone.** It is here so nobody redesigns it
by accident and so the two power variants are on record.

## What it is

A chamfered box whose three sensors (IR light, camera, PIR, port side → battery side) sit in one row on a
flat front wall that presses against the diorama's back wall, 21.4 mm above the box floor. The Pi 5 +
PiSugar 3 Plus stack sits behind them, microSD end forward, USB/Ethernet out the rear, USB-C/HDMI and
PiSugar ports through a window on the port side. The spare 38 mm beside the Pi is the cable bay. A 20°
wedge stand (`v2_stand.stl`) tilts the whole box nose-down so the camera sees the floor. Extras: a
30 mm PIR shroud, a clear PETG diffuser cap for the IR lens, and a front-wall-only test plate.

## Dimensions (from the file; the README's 107 × 96 predates the review-fixes commit)

| | USB variant | PiSugar-battery variant |
|---|---|---|
| Base file | `stl/v2_base_usb.stl` | `stl/v2_base_pisugar.stl` |
| Outer, with lid | **109.3 × 103.8 × 44.8 mm** | **109.3 × 103.8 × 56.8 mm** |
| Length incl. camera hood (5) and PIR collar (3) | 114.3 | 114.3 |
| Inside | 104.5 × 99 × 40 | 104.5 × 99 × 52 |
| Walls / floor / lid | 2.4 / 2.4 / 2.4, 5 mm lid lip, 0.3 clearance | same |
| Sensor row centre height | 21.4 mm above the floor | 21.4 (the battery lifts the Pi, not the sensors) |
| Front holes | IR 19.8 round, camera 10.5 square, PIR 23.5 round | same |
| Stand footprint | 115.3 × 109.8, 20°, 5 mm front lip | same |

Full parameter list with line numbers: `MEASUREMENTS.md` §3.

## The two base variants (`power` at node_v2.scad:23)

- **`"usb"`**: no battery inside. Power comes from a bank by USB-C cable through the port-side window.
  The stack drops onto four sockets (6.4 mm, 3 deep) that take the PiSugar's hex studs.
- **`"pisugar"`**: the PiSugar 5000 mAh pack (67 × 55 × 12, clipped magnetically under the PiSugar) lies
  in a 1.5 mm tray with 3 mm of play; two 1.6 mm fences stop the stack sliding toward the sensors or the
  cable bay. Adds 12 mm of height. Charge through the same side window.

Lid, stand, shroud, diffuser and test plate are shared by both variants. `./build_v2.sh` exports both
bases plus the shared parts and seven previews (needs the manifold backend).

## Print settings used

0.2 mm layers, 3 walls, 15 % infill, no supports (hood and collar taper at 45°). Black PLA for
everything except the diffuser (clear PETG). The 2.4 mm PETG lid went opaque, which is why D3's lid is
1.0 mm.

## Why it was dropped

Side-facing on a stand cannot hang from a tree-guard rail and cannot look down into the pit. The IR
board's lens size (19 mm here, 10 mm in D3) was never measured either way.
