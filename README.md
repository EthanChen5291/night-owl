# Barn Owl (ex Silent Blocks) — handoff, as of Saturday 2026-09-26 morning

DivHacks 2026 (Columbia, Sept 26–27, track: Hack the City). This repo is a clean-room rebuild of everything
built before the event, written so a teammate or a fresh AI session can pick up any workstream without the
original chat context. Every file here was written from this handoff, not copied from the two working repos,
so that the event-day commits are the team's own (MLH rule, see §6). The working repos remain the place where
data, footage, weights and prints live.

Team: Ethan (data + model), Utsav (frontend per the plan; the DEBRIEF hands him the detector and the
deck instead, see "Open questions"), Sanjavan (vision classifier, then backtest), Bruno (hardware + rig).

## 1. The project in one paragraph

NYC's rat map is built from 311 calls, so it is a map of who complains. Health Dept inspections split into
complaint-driven and proactive (indexed) visits; the proactive ones give ~130k near-unbiased outcomes per
year. Barn Owl trains two models per H3 r9 cell × month: Model A predicts complaints from all features
("what the city sees"), Model B predicts P(active rat signs | inspected) from physical and environmental
features only, with inverse-propensity weights ("what's there"). Silence Score = percentile(B) −
percentile(A); a "silent block" is high B, low A. A backtest on real inspections is the validation. A small
Pi 5 camera node (NoIR + 850 nm IR + PIR) hangs from a tree-guard rail, detects rats, and posts tiny JSON
events that update the cell's Beta-Binomial posterior, so the sensor turns a ranking into evidence.
Must ship: (1) map with city-sees / actually-there toggle, (2) backtest chart, (3) live node trigger on stage.

## 2. Where everything lives

| What | Path | Git |
|---|---|---|
| Master plan (hour blocks, model spec, JSON contract, node spec, pitch, Q&A bank) | `~/divMap/handoff.md` | committed |
| Open-data schema + P0 finding | `~/divMap/data/SCHEMA.md` | committed, **uncommitted edits** (ACS row, rename) |
| Raw open-data downloads (~2.7 GB CSV) | `~/divMap/data/raw/open/` | gitignored |
| Baked Parquet (~222 MB, 15 tables) | `~/divMap/data/parquet/` | gitignored |
| Bake script (DuckDB) | `~/divMap/scripts/bake_open_data.py` | committed, **uncommitted edit** (ACS table) |
| three.js NYC city renderer + H3 overlay | `~/divMap/src/`, `public/city/*.json` | committed |
| Gemini product-render tool + renders | `~/divMap/tools/render_node.py`, `renders/node/` | tool committed, PNGs gitignored |
| Pi hardware handoff, test scripts, IR captures | `~/div-hacks-26/` (README, HANDOFF-pi5…, captures/) | committed on `main` |
| Enclosure CAD (OpenSCAD), STLs, previews | `~/div-hacks-26/enclosure/` | committed on local branch `enclosure-v2` (**not pushed**); `node_owl.scad` + owl previews **untracked** |
| Vision pipeline (YOLO11n detector for the Pi) | `~/div-hacks-26/vision/` | **entirely untracked** |
| Extracted + auto-labeled frames | `~/div-hacks-26/vision/frames/`, `labels/`, `frames_pruned/` | gitignored |
| Phone recording clips (19 × .MOV, ~3.0 GB, ~30 min) | `~/divMap/IMG_7777.MOV` … `IMG_7800.MOV` | untracked, in the wrong repo, see §8 |
| Working renders / diagrams | `~/Desktop/node-cad-inside/` | not a repo |
| Secrets | `~/divMap/.env` (`GEMINI_API_KEY`, `CENSUS_DATA_KEY`), `~/div-hacks-26/CREDENTIALS.txt` (Pi login, not present locally right now; ask Bruno) | gitignored |

Remotes: `~/divMap` → `github.com/EthanChen5291/ratstat` (private; renamed from divMap on 09-25; local `main`
is 1 commit ahead of origin: "dataset download"). `~/div-hacks-26` → `github.com/brubru6707/div-hacks-26`
(Bruno's; origin `main` last commit "Add Pi login to README"; the 9 enclosure commits exist only locally).

Naming: the project was "Silent Blocks" until the evening of 09-25, now "Barn Owl"; "silent block" is still
the name of the thing the model finds. Product/domain: ratst.at. Node id in renders: SB-01.

## 3. Timeline so far

| When | What |
|---|---|
| 09-23 | City renderer built (43.6k buildings, trees, bridges, H3 overlay on synthetic `cells.fixture.json`). Pi 5 node verified: camera, PIR, PIR-triggered IR captures all pass. First exploratory CSV pulls in `~/divMap/.scratch/` (superseded). |
| 09-24 | Enclosure v2 (side-facing box on a 20° stand, USB and PiSugar base variants). |
| 09-25 early | Gemini product renders: face styles A/B/C on v2, then face-down concepts D–H, then D1–D6 variants of D. **Decision: face-down mount, concept D, D3 "band" look.** |
| 09-25 day | Enclosure D3 (face-down band box + indexed hanger) modelled, fit-checked, STLs exported. Vision pipeline scaffolded and dry-run on the Mac. Full open-data download (17 sources) and Parquet bake. **P0 check done: validation claim survives** (details §4). |
| 09-25 evening | ACS tract income/population/poverty added via Census API. DEBRIEF written for Utsav. Training-data questions written for Sanjavan. Recording session at Brown 20:36–21:56 (19 phone clips). Frames extracted, auto-labeled, pruned. Owl cosmetic variant of D3 previewed at 22:00. |
| 09-26 (today) | Event day. Node printed, assembled and running on the gooseneck rig (photos → `enclosure/AS-BUILT.md`). This rebuild, then API, web map and model. |

## 4. Status by workstream

### Data (Ethan) — done and documented

All 17 sources are in `data/parquet/`; `data/SCHEMA.md` has every column, key and gotcha. Highlights:

- Targets: `rodent_inspection` (3.13M rows, `inspection_type='Initial'` = 2.16M), `complaints_rodent`
  (513k, two 311 datasets stitched at 2020), CB-month and ZIP-month all-complaint aggregates as the
  civic-engagement denominator (2020→ only).
- Features: PLUTO, DOHMH restaurant inspections (vermin codes 04K/04L/08A), DOB NB/DM permits, litter
  baskets, catch basins, parks, 2015 street trees (the tree pits the planner snaps to), ACS 2023 5-yr
  (median income, population, poverty; null for 135 park/industrial tracts → fall back to CDBG `lomod_pct`),
  census tract polygons, NOAA Central Park monthly mean temp, RMZ polygons (4 zones), 59 community districts.
- Not available anywhere: containerization rollout status. Hand-code from DSNY announcements if used.
- **P0 result** (`initial_inspections_linked.parquet`, every Initial inspection 2015-01→2026-08 with `l60`/`l180`
  = rodent complaint on the same BBL in the prior 60/180 days, and `zone` = RMZ or null): no field says
  proactive vs complaint-driven, but the BBL join shows **75–91% of Initial inspections have no prior complaint
  on the lot**, i.e. ~130k quasi-unbiased outcomes a year, half inside RMZs. Complaint-linked inspections
  find active rats **2–3× as often (≈40% vs 15–20%)**. That is the selection bias in one number and the
  reason Model B never sees complaint counts. Use `l60 = 0` rows as the Model B target and the backtest set.
- Gotchas: clip inspection dates to 2010–2026 (junk outside); 2020–21 dip is COVID; `community_board`
  formats differ between 311 and inspections (normalise to 3-digit GEOCODE); 23% of pre-2020 complaints
  have no BBL, so "linked" is an undercount.
- Tooling: `uv` is installed; `duckdb` runs via `uv run --with duckdb` (the script's shebang). No `duckdb` CLI.

### Model (Ethan, Sanjavan for the backtest) — not started (Saturday work by MLH rules)

Spec is in `plan/master-plan.md` §4: LightGBM Poisson for A, IPW-weighted classifier for B, spatial CV by
community district, RMZ/proactive slice as holdout, ablation table, rolling-origin backtest (one chart),
conformal or ensemble CI, greedy optimizer with 100 m exclusion snapped to tree pits, Beta-Binomial per cell,
SHAP top-3 reasons. Backtest window 2015-01 → 2026-08. JSON contract to freeze at hour 0 is §6 of the plan.

### Frontend / map (Utsav) — city renderer exists, no API yet

`~/divMap` is a Vite + React + three.js app (`npm run dev`, port 5173). Lower Manhattan from open data, three
lighting presets, H3 overlay coloured by percentile rank, building tint follows cell colour, hover popup with
the contract fields. `public/city/cells.fixture.json` is **synthetic** in the frozen `GET /cells` shape.
To go live, point `loadCity()` in `src/city/scene.ts` at `/cells?month=…`. The plan's frontend spec says
deck.gl + MapLibre; the built renderer is three.js. Both render H3 cells; pick one at hour 0.
Here: `city/README.md`, `city/build_city.py`, `city/cells.fixture.json`.

### Node hardware (Bruno) — verified 09-23, printed and running 09-26 (see `enclosure/AS-BUILT.md`)

Pi 5 Rev 1.1, Debian 13 Trixie 64-bit, Arducam IMX219 NoIR on CAM0 (needs `dtoverlay=imx219,cam0`),
HC-SR501 PIR on GPIO4, one 850 nm board on its own power bank. All four tests pass; 25 IR-lit captures in
`captures/` (note the magenta NoIR cast).
**Constraints that changed the plan:** `picamera2` is not installed and the Pi has no internet (802.1X Wi-Fi).
Everything on the Pi therefore uses `rpicam-still`/`rpicam-vid` and offline aarch64 wheels. Direct
Mac→Pi Ethernet is link-local only and flaky; for the event use a switch with DHCP or static IPs both ends.
Full instructions: `node/HANDOFF-pi5-camera-pir-node.md`, `node/README-pi.md`.

### Enclosure (Bruno prints, Ethan designs) — D3 printed and assembled 09-26; as-built deltas in `enclosure/AS-BUILT.md`

Three design lines in `enclosure/`:

| Line | What | State |
|---|---|---|
| v2 (`node_v2.scad`) | side-facing box on a 20° stand, 107×96×45 mm | printed once; leave alone |
| **D3** (`node_d3.scad` + `hanger.scad`) | face-down box, sensors flat on a frosted PETG tray whose skirt is the glowing band, Pi visible through a 1 mm clear PETG lid, L-arm with V-groove foot + fan-shaped index plate, tilt 0–90° in 15° steps. Outer 95×99×49 mm. | STLs exported, fit check empty (0 mm³ overlap). **Not printed yet.** |
| owl (`node_owl.scad`) | D3 with rounded 9 mm corners, a heart-shaped "facial disc" recess on the tray, feather-comb vents. Cosmetic only, hardware positions identical. | previews only (22:00 last night), no STLs, not in `build_d3.sh`, untracked |

Print order and settings are in `enclosure/D3_NOTES.md` (tray first, 25 min, to check the three boards drop
into their fences). Print files: `enclosure/stl/d3_{body,lid,tray}.stl`, `hanger_{arm,sector,pin}.stl`.
**Unverified assumption:** the IR board is drawn as 21×29 mm with a 10 mm lens at centre; nobody has measured
the real board. Measure before printing the tray (`led_board`, `led_lens_d`, `led_lens_off`).
Hardware: M4×30 + nut (pivot), 2× M3×8 (sector), 2× M3×8 (lid, optional), 2 zip ties, hot glue.

Aim: `enclosure/aim-coverage.png` works out that from a 60 cm rail, straight down covers ~67×50 cm of pit,
and a 45° tilt covers ~127 cm of floor out to the far rail. Rats run along the inside of the guard, so the
tilt matters; the indexed hanger makes it a field setting rather than a design change. In the diorama
(faceplate 25 cm up) straight down sees 22 cm of floor; 45° sees the floor plus 12 cm of the far wall.

Renders for the deck: `renders/hero.png`, `situ.png` (node on a tree guard at night), `top.png`,
`variants-sheet.png` (D1–D6), `concepts-sheet.png` (D–H). Regenerate with `renders/render_node.py`
(needs `GEMINI_API_KEY`, model `gemini-3-pro-image`, refs from `enclosure/preview`).
The cyan glow is a demo-only touch; a field node is dark.

### Vision / detector (owner per RUNBOOK: Sanjavan; per DEBRIEF: Utsav) — frames labeled, nothing trained

What is built (`vision/RUNBOOK.md` is the step-by-step):
- Model: YOLO11n, 2 classes (rat = the Forum Novelties prop, person), 416 px, grayscale (`GRAY=True` in both
  `make_dataset.py` and `detect.py`), fine-tuned from COCO, exported to ONNX, run on the Pi CPU with onnxruntime.
- `vision/pi/detect.py`: letterbox → ONNX → NMS → floor rule (`FLOOR_Y=0.40`) → person suppression → 3 hits →
  event (max 1 per 2 s) → POST `/event` per the contract → LED blink. Full frame stays in RAM; only the rat
  crop is base64-encoded. `NODE_ID=demo-01`, `DEMO_H3=892a100d2c3ffff`.
- `vision/pi/camera.py`: `rpicam-vid` raw YUV420 to stdout, 640×480 @15, gain 8, 30 ms shutter, greyworld AWB.
  `grab_frames.py`, `selftest.py` (system/camera/stream/PIR/detector), `ir_check.py` (is the IR light on?).
- Zero-training fallback ready: `pi/world_rat_person.onnx` (YOLO-World, "stuffed animal"+"person", 50 MB,
  not in this repo). 0.80 on the prop photo, ~4× slower, fires on hoodies/bags. Use it for the hour-6 gate.
- Offline wheels for Python 3.13 aarch64 in `pi/wheels/` (onnxruntime, numpy, opencv-headless). If the Pi's
  Python differs: `./pi/bundle_wheels.sh 3.12`.

Data state this morning (`~/div-hacks-26/vision/`):

| | Count |
|---|---|
| Frames kept in `frames/` | 3,186 |
| Frames moved to `frames_pruned/` (blur / walk-in / duplicate) | 866 |
| Label files | 3,186 |
| Label files with at least one box | 2,176 |
| Clip tags | 19 (bed_a/b/c, clutter_h, corr_d/f, stair_e, stairtop_g, r3_a–e, new_a–f) |
| `dataset/`, `runs/rat/`, `pi/rat.onnx` | absent → **not trained** |

The frames came from the 19 phone .MOV clips (1080p, mostly landscape, ~30 min total) via
`extract_frames.py`; the tags do not match the IMG_ filenames, so the clips were renamed or copied before
extraction. Whether `review.py` (hand-fixing of boxes) has been run over all frames is not recorded;
label files were last touched 21:59, after pruning at 21:22, so at least a pass happened. Treat the
labels as reviewed-in-part until someone confirms. No rig (Pi camera) clips exist yet: everything so far
is phone footage, so the NoIR/IR colour domain is only covered by the grayscale conversion.

Open questions for Sanjavan are in `vision/HANDOFF-sanjavan-training-data.md` (detector vs crop
classifier, prop-only vs real rats, correlated frames, stratified val split, autolabel bias on dark
floors, whether `person` earns its keep, synthetic paste positives, event-level metric, Sunday retrain rule).

### Pitch and deck — script written, deck not started

3-minute script and Q&A one-liners are in `plan/master-plan.md` §10; the narrative for a newcomer is
`node/DEBRIEF-utsav.md`. "What's real" slide content is §12. Claims to be careful with: risk ranking not
population; PIR does not detect rats; the prop's glass eye glints under IR, so phrase the eyeshine line so
the demo crop doesn't contradict it. The detector is honestly "a prop detector trained on ~N frames from the rig".

## 5. Decisions made (and why)

1. **Face-down mount from a rail arm, not a side-facing box on a stand** (09-25). Story: clamps to the
   ~60 cm tree-guard rail over a tree pit, looks down into where rats run.
2. **Concept D body, D3 "band" surface**: lower 12 mm frosted band glows all round. D1 (full glass top) is
   the one-print path if time is short; D3 needs three single-material parts.
3. **Printed frosted PETG faceplate, not acrylic.** Hanger arm with bolt/zip-tie slots instead of a sized clamp.
4. **Tilt via the indexed sector plate, never a wedge on the body**, so the body prints flat.
5. **YOLO11n detector instead of the plan's 96×96 crop classifier**, because picamera2 (frame-diff crops)
   is unavailable and the Pi is offline; YOLO localises in one pass. Not final: Sanjavan may overrule (Q0).
6. **Prop-only training** for the demo; real-rat data is a roadmap experiment, not in the demo model.
7. **Grayscale training and inference** so phone frames and NoIR frames share one domain.
8. **Model B leakage rule**: no complaint or inspection counts as features. **`l60 = 0` Initial inspections
   are the quasi-unbiased target.**
9. Sponsor add-ons only after hour 20, max 6 team-hours: Tiger Data, Capital One Nessie, .Tech, DigitalOcean.
   Tavily dropped.

## 6. Known conflicts and risks

- **Roles diverge between documents.** The plan has Utsav on frontend and Sanjavan on vision; the DEBRIEF
  (written for Utsav, remote) gives him the detector and the deck. Settle at hour 0.
- **Frontend stack**: plan says deck.gl + MapLibre; what exists is three.js. Decide at hour 0.
- **Node spec drift**: plan §7 says AM312 PIR, two IR boards, picamera2 dual-stream, tiny CNN crop classifier.
  Reality: HC-SR501, one IR board, rpicam-vid, YOLO11n. The plan file was not updated.
- **Pi logistics** are the hour-6 gate risk: offline wheel install (Python version must match 3.13), flaky
  link-local Ethernet, `picamera2` absent.
- **IR board dimensions unmeasured** before the tray print.
- **No rig footage**: the detector has only phone frames; the first rig clips happen at the venue.
- **MLH rules**: all scripts above are pre-event spikes and must be rewritten/committed at the event under
  the team's own names. Footage, data downloads, hardware and CAD are fine. **This repo is that rewrite.**
- **Dates in the docs**: the DEBRIEF and RECORDING say "Thursday" for the 09-25 session; 09-25 was a Friday.

## 7. Next steps (from the plan, adjusted to where things stand)

Hour 0–1, everyone: freeze the JSON contract (§6 of the plan), write fixtures (`cells.json`, `plan.json`,
`queue.json`), settle roles and the frontend stack.

- **Ethan**: commit the four pending divMap edits; feature table v1 (DuckDB, H3 r9 × month) from
  `data/parquet/`; Model A / Model B / IPW; spatial CV; indexed holdout; then backtest + optimizer.
- **Bruno**: measure the IR board, fix `led_board`/`led_lens_d`, print the D3 tray first, then body, lid,
  sector, arm. Pi: `scp -r pi/`, install wheels, `python3 selftest.py`, `ir_check.py`, then run
  `detect.py` with the YOLO-World fallback for the hour-6 gate. Static IPs both ends.
- **Sanjavan / Utsav (whoever owns vision)**: answer the Q0–Q9 questions, confirm review status of the
  labels, record hall clips on the actual rig per `vision/RECORDING.md` "Once you get there", then
  `prune → augment_nostring → make_dataset → train.sh → pi/rat.onnx`. Gate: mAP50 rat > 0.9 on held-out
  clips and, better, the event-level test (20 demo pushes, negatives-only reel).
- **Utsav (if frontend)**: hexes rendering from fixtures by hour 6, swap for live `/cells` after.
- Hour 24 freeze; 24–28 deck, Devpost, 2-min video, "What's real" slide, one-pager; 28–32 rehearse ×8.

## 8. Housekeeping to do before it bites

1. `~/divMap`: `git add data/SCHEMA.md scripts/bake_open_data.py package.json package-lock.json && git commit`
   (rename to ratstat + ACS table), then `git push` (main is 1 ahead).
2. The 19 `.MOV` files sit untracked in `~/divMap/` (~3.0 GB). Move them to `~/div-hacks-26/vision/clips/`
   (add `clips/` to `vision/.gitignore`) or external storage. Never commit them.
3. `~/div-hacks-26`: `git add vision/ enclosure/node_owl.scad enclosure/preview/owl_*.png DEBRIEF-utsav.md`
   on `enclosure-v2`, then push the branch (`git push -u origin enclosure-v2`) so Bruno's repo has the CAD.
   `vision/.gitignore` already excludes frames, labels, dataset, runs, `*.pt`, `*.onnx` (except the World
   fallback) and wheels. `runs/` and `weights/` at the repo root are ~350 MB and should be gitignored too.
4. `CREDENTIALS.txt` (Pi login) is referenced by the README but not present locally; get it from Bruno.
5. `~/divMap/.scratch/` (Sep 23 exploratory CSVs and screenshots) is gitignored and superseded; ignore it.

## 8b. Corrections found during the rebuild (2026-09-26)

Things the rebuild turned up that contradict the sections above. The sections above are left as written on
Saturday morning; trust these lines and `enclosure/MEASUREMENTS.md` §5 where they differ.

- **Band height**: the frosted tray skirt that glows is 21.2 mm on D3 (22.0 on the owl), not 12 mm. No
  12 mm value exists in the CAD.
- **D3 envelope**: 95.2×99.2×48.8 mm is the body alone; the tray and lid skirts stand 1.4 mm proud, so the
  printed envelope is 98.0×102.0×48.8 mm (STL bounding boxes agree), 106 mm wide with the sector plate.
- **v2 dims**: the current `node_v2.scad` echoes 109.3×103.8×44.8 mm (USB base) / 56.8 (PiSugar), 114.3
  long with the camera hood and PIR collar. The 107×96×45 figure predates the review-fixes commit.
- **IR lens**: v2 drew a 19 mm lens barrel, D3 cuts a 10 mm hole for the same board. One is wrong; measure.
- **Fit check**: `fit_body` and `fit_lid` are truly empty; `fit_tray` exports a zero-volume sheet at z=1.2 mm
  where the ghost boards touch the tray face. "0 mm³" holds, but the grep-for-empty recipe fails for the tray
  with OpenSCAD 2026.09.23. `enclosure/HANDOFF-D3.md` gives a volume-based check.
- **Aim numbers**: from 60 cm straight down the IMX219 covers 54×72 cm, not 67×50; the tilt sweeps the narrow
  48.8° axis. At 45° the floor is covered from 23 cm out to the far rail at 127 cm plus 12 cm up its post.
  See `enclosure/aim-coverage.png`.
- **Demo cell**: `892a100d2c3ffff` centres at 27th St & 6th Ave, north of the Lower Manhattan renderer bbox
  (south of 14th St). Either widen the bbox to ~40.756 N or pick a demo cell inside it. `city/make_fixture.py`
  appends it anyway.
- **Source count**: §4 says 17 data sources but names 16 distinct downloads (counting both 311 datasets and
  CDBG). `data/SCHEMA.md` lists what it can name.
- **`groove` variable**: Bruno's HANDOFF-D3 mentions a `groove` parameter in `hanger.scad`; it does not exist,
  the V-groove is hard-coded. hanger.scad's "corner swings 59 mm" comment is the v2 box; D3 swings 53.5 mm.

## 9. What is in this repo

```
plan/master-plan.md                 the team master plan (§1–§12; §6 is the frozen JSON contract)
data/SCHEMA.md, README.md           sources, columns, join keys, P0 result (with the ACS row)
data/bake_open_data.py              CSV → Parquet (DuckDB), --download / --acs / --p0
city/README.md, build_city.py       city renderer docs and the buildings/trees bake
city/make_fixture.py                generates the three synthetic contract fixtures below
city/cells.fixture.json, plan.fixture.json, queue.fixture.json
web/                                Vite + React + three.js map (hex overlay, toggle, popup, plan pins, event feed, backtest chart)
api/                                FastAPI backend serving the contract (main.py, store.py, posterior.py, tests, fake_event.sh)
node/README-pi.md, HANDOFF-pi5-camera-pir-node.md   Pi setup, login route, gotchas, the four tests
node/DEBRIEF-utsav.md               the narrative for a newcomer
node/pir_test.py, trigger_capture.py
enclosure/MEASUREMENTS.md           every dimension pulled from the live CAD in ~/div-hacks-26/enclosure
enclosure/HANDOFF-D3.md, D3_NOTES.md, V2_NOTES.md, README.md   how the CAD works, print + assembly
enclosure/aim_coverage.py, aim-coverage.png   camera coverage vs tilt (the CAD itself stays in Bruno's repo)
vision/RUNBOOK.md, RECORDING.md, HANDOFF-sanjavan-training-data.md
vision/*.py, train.sh               extract → autolabel → review → prune → augment → make_dataset → train → eval_events
vision/pi/*.py, bundle_wheels.sh, README.md   camera, detect, grab_frames, selftest, ir_check
renders/render_node.py, README.md   the Gemini render tool (PNG outputs gitignored)
model/  feature table, Model A/B, backtest, scoring → model/out/
```

The CAD (SCAD sources, STLs, previews) is not rebuilt here: the hardware is mostly done, so this repo
records its measurements and lives with the parametric sources in `~/div-hacks-26/enclosure/`.
Binary assets that only exist in the working repos and are not recreated here: the IR sample capture,
the YOLO-World fallback ONNX, the offline wheels, the Gemini deck renders and the phone footage.
