# NightOwl — master plan (DivHacks 2026, Hack the City)

Team plan for the 36-hour build. Rewritten at the event from `README.md` (the handoff). Other files
cross-reference sections here by number; do not renumber. Section 6 (JSON contract) is frozen at hour 0
and changes only by a team decision written back into this file.

Event: Sat 2026-09-26 12:00 → Sun 2026-09-27 24:00 (36 h). Hour N below = Sat 12:00 + N h.

---

## §1 Pitch in one paragraph

NYC's rat map is built from 311 calls, so it is a map of who complains, not of where rats are. The Health
Department's rodent inspections split into complaint-driven visits and proactive (indexed) visits; the
proactive ones give ~130k near-unbiased outcomes a year, half inside the four Rat Mitigation Zones. NightOwl
trains two models on every H3 resolution-9 cell × month. Model A predicts complaints from all features:
"what the city sees". Model B predicts P(active rat signs | inspected) from physical and environmental
features only, with inverse-propensity weights, trained on Initial inspections with no prior complaint on the
lot: "what's actually there". Silence Score = percentile(B) − percentile(A); a silent block is high B, low A.
A rolling backtest on real inspections is the validation, not a story. A small Pi 5 camera node (NoIR camera,
850 nm IR, PIR) hangs face-down from a tree-guard rail, detects rats on-device, and posts tiny JSON events
that update the cell's Beta-Binomial posterior. The sensor turns a ranking into evidence, and the model tells
the city where to hang the sensor.

Must ship: (1) map with a city-sees / actually-there toggle, (2) backtest chart, (3) live node trigger on stage.

## §2 Team and roles

| Person | Lane | Owns |
|---|---|---|
| Ethan | data + model | feature table, Model A/B, IPW, spatial CV, holdout, optimizer, posterior, SHAP, API server |
| Utsav | frontend | map, toggle, popup, backtest chart, live event feed, fixtures wiring |
| Sanjavan | vision, then backtest | Q0–Q9 answers, rig clips, label review, train → `pi/rat.onnx`; from hour ~14 the backtest chart with Ethan |
| Bruno | hardware + rig | IR board measurement, D3 prints, Pi bring-up, wheels, selftest, static IPs, diorama, stage rig |

Role conflict (README §6): this plan puts Utsav on frontend and Sanjavan on vision. The DEBRIEF written for
Utsav (remote) gives him the detector and the deck instead. Settle at hour 0, before the contract freeze:

- Option 1 (this plan): Utsav frontend, Sanjavan vision → backtest. Default if Sanjavan is on site.
- Option 2 (DEBRIEF): Utsav detector + deck, Sanjavan frontend then backtest. Pick if Utsav cannot run the
  three.js app locally or Sanjavan prefers the map.
- Either way one person owns `vision/`; the other never touches it. Write the decision in the table above.

Shared rules: everything is committed to this repo under the team's names during the event (MLH). No one
copies from the two working repos. `main` is always demoable: fixtures first, live data after.

## §3 Hour-by-hour blocks

Clock: h0 = Sat 12:00, h6 = Sat 18:00, h12 = Sun 00:00, h18 = Sun 06:00, h20 = Sun 08:00, h24 = Sun 12:00,
h28 = Sun 16:00, h32 = Sun 20:00, h36 = Mon 00:00. Confirm the judging slot at check-in and pull the
rehearsal block to end at least one hour before it.

### Gates

| Hour | Gate | Pass condition |
|---|---|---|
| 0–1 | Contract freeze + fixtures | §6 agreed, `cells.json`, `plan.json`, `queue.json` in the repo, roles and frontend stack settled |
| 6 | First integration | Hexes render from fixtures; Pi passes `selftest.py`; `detect.py` with the YOLO-World fallback fires an event that lands in `/queue` |
| 12 | Model A/B v1 | Both models train, spatial CV numbers exist, `/cells` serves real scores for one month |
| 18 | Backtest chart | Rolling-origin precision@k plotted, silent blocks vs 311 baseline, on real inspections |
| 20+ | Sponsor add-ons | Only if the three must-ships are green; max 6 team-hours total |
| 24 | Freeze | No new features. Bug fixes and copy only |
| 24–28 | Deliverables | Deck, Devpost, 2-min video, "What's real" slide, one-pager |
| 28–32 | Rehearse ×8 | Full run with the live node each time, one fallback drill |

### Per-person lanes

**Hour 0–1, everyone.** Freeze §6. Write the three fixture files by hand in the exact shapes. Settle roles
(§2) and frontend stack (§8). Bruno measures the IR board before anything prints.

**Ethan (data + model)**

| Hours | Work |
|---|---|
| 0–1 | Contract, fixtures, commit the four pending divMap edits (SCHEMA ACS row, bake script, rename) |
| 1–5 | Feature table v1: DuckDB over `data/parquet/`, H3 r9 cell × month, 2015-01 → 2026-08 |
| 5–6 | Minimal API serving fixtures at the four routes; hand off to Utsav |
| 6–11 | Model A (LightGBM Poisson) and Model B (IPW binary), propensity model, spatial CV by CD |
| 11–12 | `/cells` live for the latest month; percentiles, silence, first CI |
| 12–16 | Indexed/RMZ holdout, ablation table, leakage check, SHAP top-3 per cell |
| 16–18 | Rolling-origin backtest with Sanjavan; one chart |
| 18–22 | Greedy optimizer → `/plan`; Beta-Binomial posterior → `POST /event` updates `score_b` |
| 22–24 | Server hardening: canned event path, restart script, CORS, `generated_at` |
| 24–28 | "What's real" slide, model slide, numbers for the deck |
| 28–32 | Rehearsal, Q&A bank |

**Utsav (frontend)**

| Hours | Work |
|---|---|
| 0–1 | Contract, `cells.json` fixture (synthetic, right shape), pick renderer (§8) |
| 1–6 | Hexes from fixtures, percentile colouring, toggle A/B/silence, hover popup |
| 6–12 | Point at live `/cells?month=`; month selector; `/plan` nodes as pins |
| 12–18 | Backtest chart component (reads a static JSON Ethan writes); live event feed polling `/queue` |
| 18–24 | Stage polish: dark preset, the demo cell highlighted, event animation on the hex |
| 24–28 | Deck visuals, screen recording for the 2-min video |
| 28–32 | Rehearsal driver: runs the laptop on stage |

**Sanjavan (vision → backtest)**

| Hours | Work |
|---|---|
| 0–1 | Answer Q0–Q9 in `vision/HANDOFF-sanjavan-training-data.md`; confirm label review state |
| 1–4 | Rig clips at the venue on the actual Pi camera per `vision/RECORDING.md` |
| 4–6 | Hour-6 gate with Bruno: YOLO-World fallback fires end to end |
| 6–12 | `prune → augment_nostring → make_dataset → train.sh`; export ONNX; gate mAP50 rat > 0.9 on held-out clips |
| 12–14 | Event-level test: 20 demo pushes, negatives-only reel; install `pi/rat.onnx` |
| 14–18 | Backtest with Ethan: rolling-origin loop, precision@k, the chart |
| 18–24 | Sunday retrain rule: retrain only if the reel shows a false-fire class the demo will hit |
| 24–28 | Devpost text, video edit |
| 28–32 | Rehearsal, runs the prop |

**Bruno (hardware + rig)**

| Hours | Work |
|---|---|
| 0–1 | Measure the IR board (`led_board`, `led_lens_d`, `led_lens_off`); fix the SCAD; start the D3 tray print (25 min) |
| 1–3 | Pi: static IPs both ends (switch with DHCP or fixed addresses), `scp -r pi/`, install offline wheels, `selftest.py`, `ir_check.py` |
| 3–6 | Tray fit check (three boards drop into fences), then body, lid, sector, arm prints; hour-6 gate with Sanjavan |
| 6–12 | Assemble D3, hanger, tilt setting; power (bank for IR, Pi supply); cable strain relief |
| 12–18 | Diorama: tree-guard section, rail at 25 cm, floor, prop on a stick; set tilt for the diorama (45°) |
| 18–24 | Stage kit: spare SD image, spare power bank, Ethernet cable + switch, the prop, tape; canned-event curl on the laptop |
| 24–28 | Hero photo of the printed node for the deck; one-pager hardware section |
| 28–32 | Rehearsal: handles node and prop, times the trigger |

### Sponsor add-ons (hour 20+, max 6 team-hours total)

| Sponsor | Use | Cost |
|---|---|---|
| Tiger Data | Store `/event` rows in a hypertable; `/queue` reads from it | 2 h, Ethan |
| Capital One Nessie | Mock "abatement budget" per CD to cap `k` in `/plan` | 1.5 h, Utsav |
| .Tech | Domain for the demo map | 0.5 h |
| DigitalOcean | Host the API so the Pi posts over Wi-Fi from the hall | 2 h, Ethan/Bruno |

Tavily dropped. None of these may touch the must-ships. If hour 20 arrives and any must-ship is red, skip all.

## §4 Model spec

### Unit and window

- Unit: H3 resolution 9 cell (~0.1 km², roughly a block face group) × calendar month.
- Window: 2015-01 → 2026-08. Inspection dates clipped to 2010–2026 upstream; 2020–21 dip is COVID (add a
  month dummy, do not drop).
- Source: `data/parquet/` (15 tables baked by `data/bake_open_data.py`), columns in `data/SCHEMA.md`.
- Keys: BBL → PLUTO centroid → H3 r9; point sources → H3 r9 directly; polygon sources (RMZ, CD, tracts) →
  cell centroid within.

### Feature table

Grouped by source. "B" = allowed in Model B. Model A gets everything.

| Source | Features (per cell × month unless static) | B |
|---|---|---|
| PLUTO | building count, residential units, lot area, floor-area ratio, share of 1–2 family, share pre-1940, vacant-lot share, commercial share, mixed-use share | yes |
| DOHMH restaurant inspections | restaurant count; count and share of inspections with vermin codes 04K, 04L, 08A in the trailing 3 and 12 months | yes |
| DOB permits | NB (new building) and DM (demolition) permits issued in the trailing 3, 6, 12 months | yes |
| Litter baskets | basket count in cell, count in ring-1 neighbours | yes |
| Catch basins | basin count in cell | yes |
| Parks | park area share, adjacency to a park (ring-1) | yes |
| 2015 street trees | tree count, tree-pit count, share of trees with guards | yes |
| ACS 2023 5-yr (tract) | median household income, population, poverty rate; where null (135 park/industrial tracts) use CDBG `lomod_pct` as the fallback low-income share | yes |
| NOAA Central Park | monthly mean temperature, same month previous year, 3-month lag | yes |
| RMZ | in-zone flag (4 zones), zone id | yes (see note) |
| Community district | CD id (grouping key only, not a feature in B) | grouping only |
| Rodent complaints (311) | complaints in cell in trailing 1, 3, 12 months; ring-1 complaint counts; CB-month and ZIP-month all-complaint totals as the civic-engagement denominator (2020→ only) | **no** |
| Rodent inspections | prior inspection count, prior active-sign rate, days since last inspection | **no** |
| Month | month-of-year, year, COVID dummy | yes |

RMZ note: in-zone is a policy choice, not physical. Keep it in B for v1 because it changes inspection
frequency (needed by the propensity model), then run the ablation without it. If B's ranking outside RMZs
does not move, keep it.

### Model A: what the city sees

- Target: rodent complaints in cell × month (count).
- LightGBM with Poisson objective, log-exposure = log(1 + residential units).
- All features above, including lagged complaints and inspection history.
- Output `score_a` = predicted complaints per month; `pct_a` = percentile of `score_a` across cells for that
  month.

### Model B: what's there

- Target: for Initial inspections with `l60 = 0` (no rodent complaint on the same BBL in the prior 60 days),
  binary active rat signs = 1 / 0. These are the quasi-unbiased outcomes (README §4, P0 result).
- Features: physical/environmental only (the "yes" rows). No complaint counts, no inspection history.
- Weights: inverse propensity. Propensity model = LightGBM binary on P(cell × month receives an `l60 = 0`
  Initial inspection) using the B features plus RMZ and CD. Weight = 1 / clip(p̂, 0.02, 1). Stabilise
  with the marginal inspection rate. Report effective sample size.
- Output `score_b` = P(active | inspected), calibrated (isotonic on the CV folds); `pct_b` = percentile of
  `score_b` across cells for that month, restricted to cells with any residential or commercial floor area.

### Leakage rule

Model B never sees a complaint count, an inspection count, a prior inspection outcome, or anything derived
from them (including the 311 denominators). The propensity model may see inspection history; its output
enters B only as a weight. Grep the B feature list against the forbidden columns before every train.

### Validation

- Spatial CV: 5 folds grouped by community district (59 CDs). No cell appears in two folds.
- Holdout: the RMZ/proactive slice. Hold out all `l60 = 0` Initial inspections inside RMZs for the last 12
  months; report AUC, Brier, and precision@k of B on it.
- Ablation table (for the deck, one row each): B full; B without RMZ; B without ACS; B without restaurant
  vermin codes; B unweighted (no IPW); A's features into B's target (the leakage row, to show it "wins" on
  complaint-linked inspections and loses on the proactive slice).

### Rolling-origin backtest (the one chart)

- Origins: every month from 2016-01 to 2026-07. Train on data before the origin, score all cells, rank.
- Positives: next-month Initial inspections with `l60 = 0` that found active rat signs.
- Metric: precision@k for k in {50, 100, 200} cells, plotted over origins.
- Lines: NightOwl silent blocks (top-k by silence score) vs baseline of 311 ranking (top-k by trailing
  3-month complaints) vs B alone. Shade the 2020–21 dip.
- Output: `backtest.json` (origin, k, method, precision) that the frontend chart reads. One PNG for the deck.
- Owner: Ethan builds the loop, Sanjavan runs it from hour 14 and makes the chart.

### Uncertainty

- Conformal: split-conformal on the CV out-of-fold residuals gives `ci_b = [lo, hi]` at 80%.
- Fallback if time is short: 5-seed LightGBM ensemble, `ci_b` = min/max across seeds.

### Silence Score

`silence = pct_b − pct_a`, range −100..100. Positive = more rats than complaints (silent block). Negative =
more complaints than rats (loud block). Shown as the third toggle state on the map.

### Node-placement optimizer (`/plan`)

- Greedy: pick the cell with the highest expected gain, exclude every tree pit within 100 m, repeat k times.
- Expected gain = silence-weighted uncertainty: `(ci_b[hi] − ci_b[lo]) × max(silence, 0) / 100`, so nodes go
  where the model is both confident-of-silence and least certain.
- Each pick snaps to the nearest 2015 street-tree pit in the cell (`tree_id`, lat, lon). Cells without a pit
  are skipped.
- `reason` = the top SHAP feature name in a sentence.

### Beta-Binomial posterior (`POST /event`)

- Per cell: prior `alpha = score_b × n0`, `beta = (1 − score_b) × n0`, `n0 = 10`.
- Each accepted event adds `alpha += conf`, `n_events += 1`. `score_b_updated = alpha / (alpha + beta)`.
- Events with `conf < 0.5` or fewer than 3 hits are logged but do not update.
- A rat-free night from a node (heartbeat, not in the contract v1) would add to `beta`; roadmap.

### Reasons

SHAP TreeExplainer on B, top 3 features by |shap| per cell for the served month. Feature names mapped to
plain phrases in the frontend (e.g. `rest_vermin_12m` → "restaurant vermin violations, last 12 months").

## §5 Data sources summary

17 sources, all downloaded and baked to Parquet before the event (data and downloads are allowed by MLH;
the bake script is rewritten here). Columns, keys, gotchas: `data/SCHEMA.md`.

| # | Source | Role | Grain | Notes |
|---|---|---|---|---|
| 1 | DOHMH rodent inspections | target (B), backtest | inspection, BBL | 3.13M rows; `Initial` = 2.16M; `l60`/`l180`/`zone` in `initial_inspections_linked.parquet` |
| 2 | 311 rodent complaints, legacy (pre-2020) | target (A) | complaint, BBL/point | 23% lack BBL; stitched with #3 |
| 3 | 311 rodent complaints, 2020→ | target (A) | complaint, BBL/point | together 513k rows |
| 4 | 311 all complaints, 2020→ | civic-engagement denominator (A only) | CB-month, ZIP-month | normalise CB to 3-digit GEOCODE |
| 5 | PLUTO | features | BBL | lot centroid → H3 |
| 6 | DOHMH restaurant inspections | features | inspection, restaurant | vermin codes 04K, 04L, 08A |
| 7 | DOB permits (NB, DM) | features | permit, BBL | new building, demolition |
| 8 | DSNY litter baskets | features | point | |
| 9 | DEP catch basins | features | point | |
| 10 | Parks properties | features | polygon | |
| 11 | 2015 street tree census | features, planner snap | tree point | the tree pits `/plan` snaps to |
| 12 | ACS 2023 5-yr (Census API) | features | tract | median income, population, poverty; 135 null tracts |
| 13 | CDBG low/mod income (`lomod_pct`) | ACS fallback | tract | fills the 135 nulls |
| 14 | Census tract polygons | join | polygon | tract → cell |
| 15 | NOAA Central Park monthly temp | features | month | |
| 16 | Rat Mitigation Zone polygons | feature, holdout | polygon | 4 zones |
| 17 | Community districts | CV grouping | polygon | 59 CDs |

Not available anywhere: containerization rollout status (DSNY bin mandates by district and date). Hand-code
from DSNY announcements if a feature is wanted; not in v1.

Gotchas that bite: clip inspection dates to 2010–2026; COVID dip 2020–21; `community_board` formats differ
between 311 and inspections; pre-2020 "linked" counts are undercounts.

## §6 The frozen JSON contract

Frozen at hour 0. Every consumer (frontend, node, fixtures, server) codes against this text. H3 ids are
resolution-9 strings. Percentiles 0–100. Timestamps ISO 8601 UTC. Months `YYYY-MM`.

```
GET /cells?month=YYYY-MM → {"month":"2026-08","generated_at":ISO,"cells":[{"h3":"892a100d2c3ffff","score_a":float (predicted complaints per month),"score_b":float (P(active|inspected)),"pct_a":0-100,"pct_b":0-100,"silence":pct_b-pct_a,"ci_b":[lo,hi],"posterior":{"alpha":float,"beta":float,"n_events":int},"reasons":[{"feature":str,"shap":float} ×3],"cd":"101","rmz":str|null,"n_inspections":int,"last_event_at":ISO|null}]}
```

```
GET /plan?month=YYYY-MM&k=int → {"month","k","nodes":[{"rank":1,"h3","lat","lon","tree_id":str,"expected_gain":float,"silence":float,"reason":str}]}
```

```
GET /queue?limit=int → {"events":[<event objects as posted, newest first, with "received_at" added>]}
```

```
POST /event ← {"node_id":"demo-01","h3":"892a100d2c3ffff","ts":ISO,"class":"rat","conf":0.91,"n_hits":3,"bbox":[x,y,w,h] normalised 0-1,"crop_b64":str,"fw":"0.1.0"} → 200 {"ok":true,"h3","posterior":{"alpha","beta","n_events"},"score_b_updated":float}
```

Fixture files: `cells.json`, `plan.json`, `queue.json` in those shapes.

Notes that do not change the shapes:

- `cells` covers the served month only; the frontend fetches one month at a time.
- `reasons` is exactly 3 entries, sorted by |shap| descending.
- `rmz` is the zone name string or `null`.
- `n_inspections` is the count of `l60 = 0` Initial inspections in the cell over the training window.
- `POST /event` returns 200 with `ok: true` even when the event does not move the posterior (low `conf`);
  malformed bodies get 400. `crop_b64` is a JPEG of the rat crop only; the full frame never leaves the Pi.
- Demo constants: `node_id = demo-01`, `h3 = 892a100d2c3ffff`. The fixtures include this cell.
- Server base URL is set once in the frontend and in `pi/detect.py` (`API_URL`).

## §7 Node spec (as built)

Written as the node actually is, per README §4 and §6. The original plan's spec is recorded below as drift.

### Hardware

| Part | As built |
|---|---|
| Compute | Raspberry Pi 5 Rev 1.1, Debian 13 Trixie 64-bit |
| Camera | Arducam IMX219 NoIR on CAM0; `dtoverlay=imx219,cam0` in config |
| Motion | HC-SR501 PIR on GPIO4 |
| Illumination | one 850 nm IR LED board on its own power bank |
| Capture | `rpicam-vid`, raw YUV420 to stdout, 640×480 @ 15 fps, gain 8, 30 ms shutter, greyworld AWB (`vision/pi/camera.py`) |
| Detector | YOLO11n, 2 classes (rat = the prop, person), 416 px, grayscale, fine-tuned from COCO, ONNX, onnxruntime on CPU |
| Fallback detector | YOLO-World `world_rat_person.onnx` ("stuffed animal" + "person"), 50 MB, ~4× slower, fires on hoodies and bags; hour-6 gate only |
| Python deps | offline aarch64 wheels for Python 3.13 in `pi/wheels/` (onnxruntime, numpy, opencv-headless); rebuild with `./pi/bundle_wheels.sh 3.12` if the Pi's Python differs |
| Network | Pi has no internet (802.1X Wi-Fi). Direct Mac→Pi Ethernet is link-local and flaky; use a switch with DHCP or static IPs both ends |
| Enclosure | D3 face-down band box, 95×99×49 mm, frosted PETG tray + clear lid, L-arm hanger with indexed sector, tilt 0–90° in 15° steps. Not printed as of Saturday morning |
| Mount | tree-guard rail, ~60 cm above the pit; diorama rail 25 cm |
| Fasteners | M4×30 + nut (pivot), 2× M3×8 (sector), 2× M3×8 (lid, optional), 2 zip ties, hot glue |

### Firmware behaviour (`vision/pi/detect.py`, fw 0.1.0)

1. PIR high → start reading frames from `rpicam-vid`.
2. Letterbox → ONNX → NMS.
3. Floor rule: boxes with centre above `FLOOR_Y = 0.40` are dropped (rats are on the floor).
4. Person suppression: any `person` box suppresses `rat` boxes in the same frame.
5. 3 consecutive rat hits → one event, max 1 per 2 s.
6. POST `/event` per §6 with the base64 crop; full frame stays in RAM.
7. LED blink on success.

Test scripts: `selftest.py` (system, camera, stream, PIR, detector), `ir_check.py` (is the IR on),
`grab_frames.py` (rig clips for training). Setup: `node/HANDOFF-pi5-camera-pir-node.md`, `node/README-pi.md`.

### Coverage

From a 60 cm rail: straight down covers ~67×50 cm of pit; 45° tilt covers ~127 cm of floor out to the far
rail. Rats run along the inside of the guard, so tilt is a field setting via the sector plate. Diorama
(25 cm): straight down sees 22 cm of floor; 45° sees the floor plus 12 cm of the far wall. Use 45° on stage.

### Drift from the original plan

| Original plan | As built | Why |
|---|---|---|
| AM312 PIR | HC-SR501 PIR on GPIO4 | what was on hand; verified 09-23 |
| two IR boards | one 850 nm board | one is enough at 60 cm; second port on the tray unused |
| picamera2 dual-stream (low-res motion, hi-res crop) | `rpicam-vid` single YUV stream | `picamera2` not installed, Pi offline, no pip |
| tiny CNN on 96×96 frame-diff crops | YOLO11n grayscale detector | no frame-diff pipeline without picamera2; YOLO localises in one pass |

Not final: Sanjavan may overrule the detector choice (Q0). The IR board size (drawn 21×29 mm, 10 mm lens)
is unmeasured; measure before the tray prints. The cyan glow in the renders is demo-only; a field node is dark.

## §8 Frontend spec

### Hour-0 decision: renderer

| Option | State | Pick if |
|---|---|---|
| three.js city renderer (exists) | Vite + React + three.js, `npm run dev` on 5173; Lower Manhattan, 43.6k buildings, trees, bridges, three lighting presets, H3 overlay coloured by percentile, building tint follows cell colour, hover popup with contract fields, reads `public/city/cells.fixture.json` | Utsav can run it in 15 minutes. Default. |
| deck.gl + MapLibre (original plan) | nothing built | the three.js app will not build on Utsav's machine, or citywide extent is needed for the judges |

The three.js renderer only covers Lower Manhattan. That is fine for the demo: the demo cell and two of the four
RMZs are there. Citywide is a roadmap line.

To go live: point `loadCity()` in `src/city/scene.ts` at `/cells?month=…`. Keep the fixture path as the
fallback when the fetch fails.

### Views

1. **Toggle: city sees / actually there / silence.** Colours cells by `pct_a`, `pct_b`, or `silence`. One
   sequential ramp for the two percentiles, one diverging ramp centred at 0 for silence. Legend shows which.
2. **Hover popup** fields: h3, `score_a` (complaints/mo), `score_b` (P(active)), `pct_a`, `pct_b`, `silence`,
   `ci_b`, `n_inspections`, `cd`, `rmz`, `reasons` ×3 as phrases, `posterior` (alpha, beta, n_events),
   `last_event_at`.
3. **Plan layer**: `/plan?k=10` nodes as pins on tree pits, ranked, with `expected_gain` and `reason`.
4. **Backtest chart**: precision@k over origin month, three lines (silent blocks, 311 baseline, B alone), k
   selector, COVID shading. Reads `backtest.json`. Static image fallback.
5. **Live event feed**: poll `/queue?limit=20` every 2 s. New event → row in the feed with the crop
   thumbnail, and the cell pulses, its posterior and `score_b` update in the popup.
6. **Month selector**: default 2026-08.

Demo cell `892a100d2c3ffff` is pinned in the camera default view. Dark lighting preset on stage.

## §9 Demo runbook

### Must-ships

1. Map with city-sees / actually-there toggle, live from `/cells`.
2. Backtest chart on real inspections.
3. Live node trigger on stage: prop moves → event → cell updates.

### Stage kit

Laptop (frontend + API server, both local), Pi in the D3 enclosure on the diorama rail, switch + two
Ethernet cables, Pi power supply, IR power bank (charged) + spare, the prop on a stick, phone with the
canned-event curl pasted, HDMI adapter, tape.

### Trigger sequence

| Step | Who | Action | On screen |
|---|---|---|---|
| 0 | Utsav | Map open on the demo cell, "silence" view, feed panel visible, `/queue` empty | silent block highlighted |
| 1 | Bruno | Confirms IR on (`ir_check.py` ran before walking on), `detect.py` running, LED idle | — |
| 2 | Sanjavan | Waves the prop under the node at floor level for ~2 s | — |
| 3 | node | PIR fires, 3 hits, POST `/event` | feed row with crop, cell pulses, posterior n_events 0→1, `score_b` rises |
| 4 | Ethan | Reads the popup aloud: "the model said 78% and the city had zero complaints; the node just confirmed it" | popup |
| 5 | Sanjavan | Second wave | n_events 2, posterior tightens |

Total < 30 s. Rehearse until the wave-to-pixel latency is known; say it out loud in the pitch.

### Fallbacks, in order

1. Detector misses: switch to the YOLO-World fallback ONNX (`DETECTOR=world` env) and wave again. It fires
   on the prop at 0.80.
2. Node or network dead: canned event from the laptop, identical to the fixture event:

   ```
   curl -s -X POST http://localhost:8000/event -H 'content-type: application/json' \
     -d @fixtures/event.demo.json
   ```
   Say so. The "What's real" slide already lists it.
3. API dead: frontend falls back to `cells.fixture.json`; skip the trigger, show the backtest chart, show
   the node video from rehearsal.
4. Frontend dead: deck screenshots of the map and the chart, live curl in a terminal for the event.

### Pre-stage checklist (30 min before)

- [ ] Pi boots, static IP answers, `selftest.py` all pass, `ir_check.py` yes
- [ ] `detect.py` running with `pi/rat.onnx` (or fallback), `API_URL` points at the laptop
- [ ] API serves `/cells?month=2026-08` with real scores; `/queue` reset
- [ ] Frontend up, demo cell in view, feed empty
- [ ] Prop, IR bank charged, spare bank, curl fallback ready
- [ ] Laptop on power, notifications off, display mirroring tested

## §10 Pitch script and Q&A bank

### 3-minute script (~420 words)

[Slide: 311 rat map] New York has a rat map. It is built from 311 calls. So it is a map of who complains,
not where the rats are. Neighbourhoods that call get inspected, get baited, get bins. Neighbourhoods that
don't call get nothing, and the map says they are fine.

[Slide: inspections] The Health Department also does proactive inspections: inspectors walk indexed blocks
whether anyone called or not. About a hundred and thirty thousand of those a year. We linked every initial
inspection since 2015 to the complaints on the same lot. Seventy-five to ninety percent had no complaint
behind them. And inspections that follow a complaint find active rats two to three times as often. That gap
is the selection bias, in one number.

[Slide: two models] NightOwl trains two models on every H3 cell, every month. Model A predicts complaints
from everything the city knows. That is what the city sees. Model B predicts the chance an inspector finds
active rat signs, trained only on those proactive inspections, only on physical features: buildings,
restaurant vermin violations, demolitions, litter baskets, catch basins, income, temperature. Weighted so
inspection frequency doesn't bias it. That is what's actually there. Subtract the two percentiles and you get
the Silence Score. A silent block is where B is high and A is low. Rats, no calls.

[Slide: map, toggle] Here is Lower Manhattan. City sees. Actually there. Silence. These blocks light up.

[Slide: backtest] Is it real? We backtested it. Every month since 2016, train on the past, rank the city,
then check next month's proactive inspections. Silent blocks beat the 311 ranking at precision at a hundred,
on inspections the model never saw. This chart is real inspections, not a simulation.

[Slide: node] A ranking is a hypothesis. So we built the thing that checks it. A Pi 5, a no-IR camera,
850-nanometre light, a PIR sensor, in a printed box that hangs from a tree-guard rail and looks down into the
pit where rats run. It runs a detector on device and posts a two-kilobyte event: cell, time, confidence, a
crop. No video ever leaves the box.

[Live] Sanjavan. [prop wave] There. Feed. The cell pulses. Posterior updates. Model said seventy-eight
percent, city had zero complaints, node says yes. And the model tells you where to hang the next node: top
ten cells, hundred-metre spacing, snapped to real tree pits.

[Slide: what's real] Real: seventeen open datasets, both models, the backtest, the hardware, the detector.
Demo-only: the detector is trained on a prop; the glow is for you.

[Slide: close] The city already pays for the inspections. We just stopped throwing the answer away. NightOwl.
ratst.at.

### Q&A bank

| Question | Answer |
|---|---|
| Isn't this just selection bias you can't fix? | We measured it: complaint-linked inspections find rats 2–3× as often. Model B trains only on the uncomplained ones, weighted by how likely a block was to be inspected. |
| Why are proactive inspections unbiased? | Unbiased-ish, not unbiased. Inspectors walk indexed blocks on a schedule, not because someone called. The residual bias is which blocks get indexed; that's what the propensity weights correct. |
| How do you know an inspection is proactive? | No field says so. We join to complaints on the same lot: no rodent complaint in the prior 60 days means it wasn't a complaint visit. 75–91% qualify. |
| Why H3 resolution 9? | ~0.1 km², a few block faces. Small enough to place a sensor, big enough that a month has inspections in it. |
| Why not just use complaints per capita? | Per capita still measures callers. Two blocks with the same rats and different call rates look different; B doesn't see calls at all. |
| What's in the Silence Score? | Percentile of B minus percentile of A. Positive means more rats than calls. |
| Does PIR detect rats? | No. PIR wakes the camera on any warm motion. The detector decides. |
| Can the camera see people? | It looks straight down at a tree pit from 60 cm. Anything above the floor line is dropped, a person box suppresses the frame, and only a rat crop leaves the device. |
| Why 850 nm IR? | Invisible to people and rats, the NoIR sensor sees it, cheap boards. |
| Eyeshine? | Rat eyes reflect IR, and so does our prop's glass eye, which is why the demo crop has a bright dot. In the field it's a feature; here it's a coincidence. |
| Is the detector trained on real rats? | No. It's a prop detector trained on ~3,000 frames from our rig. Real-rat training is the first field experiment. We say so on the "What's real" slide. |
| Why prop-only training? | We had one night. A prop under our own IR gives frames in the right domain. Real rats would need field nights we haven't had. |
| What data is missing? | Containerization rollout: which districts got bins and when. It isn't published as a dataset. We'd hand-code it from DSNY announcements. |
| How does one event change the map? | Each cell has a Beta-Binomial posterior seeded from Model B. An event adds to alpha; the served score is the posterior mean. Ten nights of no events would pull it down. |
| Why spatial CV? | Neighbouring cells share everything. Random folds leak; grouping by community district doesn't. |
| Who would use it? | DOHMH to pick indexed blocks, DSNY to place bins, community boards to argue for resources with evidence instead of call volume. |
| What did you build before the event? | Data download, CAD, hardware bring-up, footage. All code in this repo was written at the event. |

## §11 Risks

From README §6, with the mitigation this plan assumes.

| Risk | Impact | Mitigation |
|---|---|---|
| Roles diverge (plan vs DEBRIEF) | two people on vision, nobody on the map | settle at hour 0, write it into §2 |
| Frontend stack undecided | wasted hours on a second renderer | default three.js, decide by hour 1 |
| Node spec drift (AM312, two IR boards, picamera2, crop CNN in old docs) | someone builds to the old spec | §7 is the as-built spec; old plan text is only in the drift table |
| Pi logistics: offline wheels must match Python 3.13, link-local Ethernet flaky, no picamera2 | hour-6 gate slips | static IPs both ends, wheel bundle for 3.12 ready, YOLO-World fallback for the gate |
| IR board dimensions unmeasured | tray misprints, re-print costs 25 min + | measure at hour 0, before any print |
| No rig footage | detector trained on phone frames only; NoIR domain covered only by grayscale | rig clips in hours 1–4, retrain by hour 12 |
| Labels reviewed-in-part | mAP inflated by autolabel bias on dark floors | held-out clips by tag; event-level test of 20 pushes and a negatives reel |
| Detector misses on stage | must-ship 3 fails | fallback order in §9 |
| Model B looks worse than 311 in the backtest | validation claim weakens | report it honestly; the chart still shows the gap between complaint-linked and proactive hit rates |
| MLH clean-room rule | disqualification | nothing copied from the working repos; all code committed at the event under team names |
| Doc dates wrong ("Thursday" for 09-25, a Friday) | confusion only | ignore |
| Sponsor add-ons eat the freeze | must-ships regress | hour 20+, 6 team-hours cap, none if a must-ship is red |

## §12 "What's real" slide

Say this on stage before anyone asks.

**Real data**
- 17 NYC open datasets, ~2.7 GB raw, baked to Parquet. 3.13M rodent inspections, 513k rodent complaints.
- The P0 finding: 75–91% of Initial inspections have no prior complaint on the lot; complaint-linked ones
  find active rats 2–3× as often (≈40% vs 15–20%).

**Real model**
- Model A and Model B trained at the event on the feature table; spatial CV by community district; RMZ
  holdout; ablation table.
- The backtest chart is real proactive inspections 2015–2026, rolling origin. Numbers as shown, not tuned
  after the fact.
- Confidence intervals: conformal (or a 5-seed ensemble if we ran out of time; the slide says which).

**Real hardware**
- Pi 5, IMX219 NoIR, HC-SR501 PIR, 850 nm IR board. Camera, PIR, and IR-triggered captures verified.
- Printed D3 enclosure and hanger (if the prints finished; otherwise v2 box is shown and we say so).
- On-device detection with onnxruntime; the event on stage is a real POST from the Pi.

**Demo-only / synthetic**
- The detector is a prop detector: trained on ~3,000 frames of a toy rat from our rig, not real rats. The
  prop's glass eye glints under IR.
- The map covers Lower Manhattan only.
- The cyan band glow is for the stage; a field node is dark.
- The Beta-Binomial prior strength (n0 = 10) is a chosen constant, not fitted.
- If the network fails we post the canned event by curl and say so.

**Not built**
- Containerization rollout as a feature (no dataset exists).
- Real-rat detection, multi-node deployment, negative evidence from quiet nights, citywide map.

**Not a population estimate.** NightOwl ranks blocks by risk of active signs; it does not count rats.
