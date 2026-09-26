# Enclosure
The CAD (OpenSCAD sources, STLs, previews) lives in Bruno's repo `~/div-hacks-26/enclosure/` on the local branch `enclosure-v2`, which is **not pushed** yet (`node_owl.scad` and the owl previews are untracked there too); this folder holds only the measurements and notes written from it.
`MEASUREMENTS.md` has every dimension with its SCAD variable and line; `HANDOFF-D3.md` explains the parametric model, tilt, export and fit check; `D3_NOTES.md` covers print order, materials, hardware, assembly and tilt settings; `V2_NOTES.md` records the printed-once predecessor and its USB / PiSugar bases.
`aim_coverage.py` (run `./aim_coverage.py`; uv fetches matplotlib) draws `aim-coverage.png`, the camera footprint vs hanger tilt for a real tree guard and for the diorama.
Before printing the D3 tray, measure the IR board and fix `led_board`, `led_lens_d`, `led_lens_off` in `node_d3.scad`; everything else is derived.
