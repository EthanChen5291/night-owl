# model/ — where are the rats nobody reports?

Sanjavan's node-location pipeline for Barn Owl. Written on 2026-09-26 (event day). Last updated **Sat 16:40** (hotspot click zooms in and opens the popup).

## Headline results

| Claim | Number | Where |
|---|---|---|
| **Backtest: our picks beat "go where people complain"** | **19.5% vs 15.2%** of swept lots had rats (+28%), won **108 of 119 months** (2016-01 → 2026-08) | `out/backtest.json` |
| Backtest: beats "go where rats were found before" | 19.5% vs 17.1%, won 96 of 119 months, without using inspection history | `out/backtest.json` |
| **Backtest: quiet blocks only** | **15.6% vs 8.8% random (1.8×), won 117 of 119 months** | `out/backtest.json` |
| Live loop (hour-6 gate, server side) | `api/` serving our `out/` files; one fake rat event on the demo cell: `score_b` 0.038 → 0.118, silence −1.2 → +14.4 | tested 14:00 (pre-binning scores) |
| Quiet ≠ rat-free | loudest vs quietest areas: complaints differ **17.8×**, rats found in sweeps only **2.3×** | `out/validation.json` test 1 |
| Out-of-time check | trained to 2023-12; quiet cells swept in 2024: high-risk third 20.0% vs low-risk third 7.2% | test 2 |
| No ground truth where nobody complains | **97%** of the quietest-quartile cells had no proactive sweep in 24 months, vs 55% of the loudest | `03_models.py` data_gap |
| Silent blocks (high B, low A) | **382 cells** with ≥100 homes, median income **$62k vs $92k**, limited-English households **17.1% vs 9.2%** | `out/cells.json` (`is_silent`) |
| Sensor picks | 20 sites on real tree pits, 95% never swept, median income $59k | `out/plan.json` |
| Model B accuracy | AUC **0.633** on held-out community districts (logistic baseline 0.567) | `out/metrics.json` |
| **Which buildings first** | building-level model ranks swept buildings at AUC **0.692** (vs 0.630 for the cell model); top 5 buildings for each of 519 silent blocks / node sites | `out/buildings.json` |
| **Buildings with no inspection history** (silent-block case) | building model's top picks had rats **18.5%** vs complaints 9.9% vs random 8.5% (**2.2×**), won **105 of 121 months** vs random | `out/building_backtest.json` |

Backtests are scored **only on cells DOHMH actually swept that month**. Silent blocks are rarely
inspected, so scoring on "any inspection found rats" grades the model on where DOHMH goes, not where rats are.

## Why our picks find more rats

The complaints baseline ranks blocks by **who calls**: some loud blocks aren't ratty (one East Harlem user
alone filed 5,339 complaints), and quiet ratty blocks get missed. Model B ranks blocks by **physical
conditions** and never sees complaints. The "rats found last year" baseline only works where inspectors
already went; Model B can rank any block.

What Model B relies on most (LightGBM gain, share of total, model trained to 2026-08):

| Feature | Share | Likely reason (interpretation; the model shows *what* predicts rats, not *why*) |
|---|---|---|
| building height (`floors_mean`) | 14.4% | low-rise walk-ups / rowhouses: bags on the curb, backyards, basements; high-rises often have indoor trash rooms |
| temperature (`temp_c`) | 10.7% | **seasonal, citywide:** same value for every block in a month, so it sets *when*, not *which block* |
| **trash bins required (`share_binned`)** | 8.9% | DSNY bin rules cut rats' food; **caveat:** it switches on at fixed dates, so part of this may be a time trend |
| district trash tonnage | 8.4% | more trash, more food |
| building area | 6.9% | bigger buildings, more waste |
| median income | 5.4% | **control only**, not a cause; don't present it as "poor areas have rats" |
| median building age / pre-1940 share | 5.1% / 4.6% | old buildings: cracks, gaps, old sewer connections |
| properties, street trees, population density | 3.7% / 3.0% / 2.7% | more places to nest, soil to burrow in, people making trash |

Pitch version (place features only): *"The city ranks blocks by who calls. We rank them by what attracts
rats: low-rise old buildings and heavy trash."* Per-cell `reasons[]` in `cells.json` already exclude the
seasonal features (temperature, month, district tonnage).

## Building level: which buildings to inspect first

`lots.py` trains Model B on each swept building (1.5M inspections) with the lot's own PLUTO attributes
(age, floors, units, building class, areas, vacant, has a restaurant) plus the cell features. Same spatial CV:

| | AUC (held-out districts) |
|---|---|
| cell model, same score for every building in a cell | 0.630 |
| **building model, per building** | **0.692** |
| building model averaged per cell | 0.649 |

In the backtest (ranking cells) it's a tie: 19.7% vs 19.5% of swept lots with rats, but it wins fewer months
(107 vs 108 against complaints, 91 vs 96 against prior positives). So the **cell model stays the main Model B**
(map, backtest, silence, planner), and the building model powers the per-block list in `out/buildings.json`.
Bigger buildings score higher (more units, more chances for signs), which is right for "where will an inspector
find rats". ### Building-level backtest (`07_building_backtest.py`, 121 months, top 500 swept buildings/month)

Rats range 30–150 m (NYC: Combs/Fordham 2017; Vancouver: 99% of relatives trapped in the same block), so signs
often turn up next door. Two ways to count a hit: **exact** (rats at that building) and **block** (rats anywhere on
its tax block that day).

| Method | exact | block |
|---|---|---|
| rats found at this building in the prior 24 months | **41.4%** | 89.3% |
| **building model** | **32.0%** | 89.2% |
| complaints about the building, prior 12 months | 26.2% | 82.7% |
| hexagon model | 22.5% | **90.1%** |
| random | 11.5% | 74.4% |

- Exact building: the building model beats the hexagon model in 121/121 months and complaints in 111/121, but
  **"rats found here before" wins** (rats come back to the same building). Honest: for buildings DOHMH already
  knows, re-checking past positives is the best rule.
- Block: hexagon ≈ building ≈ past positives (~89–90%); all beat complaints. If rats roam the block, the area view is enough.
- **No history (the silent-block case, ~1,000 swept buildings/month with no Initial inspection in 24 months):**
  building 18.5%, hexagon 13.0%, complaints 9.9%, random 8.5%. Complaints barely beat random here; the building
  model finds 2.2× random (beats random 105/121, complaints 86/121, hexagon 81/121 months).

Neighbour (ring-1) features were also tested: no gain (0.633 → 0.632), not used.

## Hotspot rankings (`08_hotspots.py` → `out/hotspots.json`)

Every eligible cell in `cells.json` now carries `rank_risk` / `tier_risk` (1 = highest Model B risk) and
`rank_silent` / `tier_silent` (silent cells only; 1 = biggest gap), with tiers "top 1%" (52 cells), "top 5%",
"top 10%", plus `neighborhood` and `borough`. `--boroughs Manhattan,Brooklyn` writes a re-ranked
`out/hotspots_manhattan_brooklyn.json`.

**Top 10 rat-risk hotspots** (where rats are most likely, whatever people report). Top 1% by borough: {'Bronx': 24, 'Manhattan': 27, 'Brooklyn': 1}

| # | Neighborhood | Borough | risk | silence | complaints/yr | inspect first |
|---|---|---|---|---|---|---|
| 1 | Pelham Parkway-Van Nest | Bronx | 15.7% | +21 | 7 | 2167 CRUGER AVENUE |
| 2 | Bedford Park | Bronx | 15.3% | +26 | 18 | 2914 JEROME AVENUE |
| 3 | Inwood | Manhattan | 14.7% | +36 | 12 | 232 SHERMAN AVENUE |
| 4 | Concourse-Concourse Village | Bronx | 14.4% | +30 | 15 | 111 EAST 167 STREET |
| 5 | Mount Eden-Claremont (West) | Bronx | 14.0% | +21 | 11 | 1420 GRAND CONCOURSE |
| 6 | Mount Eden-Claremont (West) | Bronx | 13.9% | +38 | 8 | 1460 MACOMBS ROAD |
| 7 | Concourse-Concourse Village | Bronx | 13.8% | +36 | 6 | 1150 COLLEGE AVENUE |
| 8 | Harlem (South) | Manhattan | 13.8% | +4 | 36 | 89 LENOX AVENUE |
| 9 | Claremont Village-Claremont (East) | Bronx | 13.7% | +75 | 1 | 1674 CARTER AVENUE |
| 10 | Washington Heights (North) | Manhattan | 13.6% | +2 | 7 | 38 SICKLES STREET |

**Top 10 silent hotspots** (rats likely, far fewer complaints than expected). Top 1% by borough: {'Manhattan': 16, 'Bronx': 16, 'Brooklyn': 7, 'Queens': 13}

| # | Neighborhood | Borough | risk | silence | complaints/yr | inspect first |
|---|---|---|---|---|---|---|
| 1 | Harlem (North) | Manhattan | 8.5% | +94 | 5 | 2918 FREDRICK DOUGLASS BL |
| 2 | Mount Eden-Claremont (West) | Bronx | 8.8% | +93 | 2 | 1570 WEBSTER AVENUE |
| 3 | Highbridge | Bronx | 6.6% | +90 | 0 | 903 SUMMIT AVENUE |
| 4 | South Williamsburg | Brooklyn | 7.2% | +88 | 1 | 265 LEE AVENUE |
| 5 | Corona | Queens | 6.1% | +87 | 3 | 55-25 98 PLACE |
| 6 | Forest Hills | Queens | 6.9% | +86 | 2 | 104-15 QUEENS BOULEVARD |
| 7 | Flushing-Willets Point | Queens | 6.2% | +85 | 2 | 43-23 COLDEN STREET |
| 8 | Norwood | Bronx | 12.6% | +82 | 9 | 3525 DECATUR AVENUE |
| 9 | Kingsbridge-Marble Hill | Manhattan | 8.5% | +80 | 9 | 5210 BROADWAY |
| 10 | East Harlem (North) | Manhattan | 8.2% | +80 | 0 | 322 EAST 126 STREET |

**On the map:** a "NYC hotspots" panel (`web/src/components/Hotspots.tsx`, tabs Silent / Rat risk, click = fly
to the cell) reads these rank fields straight from `/cells`; the cell popup shows neighborhood and tier. Both the hotspots and events panels have a minimize (–/+) button. Clicking a hotspot flies the camera in (~900 m), pulses the cell and opens its popup; clicking an event also zooms in now. Both hide
themselves on fixture data, which has no ranks.

Scope: models train and rank on all five boroughs (the silent blocks are mostly in the Bronx and Queens; dropping
them would lose data and the equity story). The 3D demo map only draws Lower Manhattan.

## Honest limits (say these before a judge does)

- **Never-swept areas can't be validated with existing data.** We tried restaurant rat violations (04K) as an
  independent check there: no clear signal (2.9% / 2.4% / 3.0% by risk tier). Not claimed. That gap is
  what the nodes are for.
- **The equity result depends on how Model A is normalised.** Per resident (used, because complaints come from
  people): silent blocks $70k / 14.9% limited-English. Raw counts: $86k / 7.6%. Per property: richer ($101k). Table in
  `out/validation.json` test 4.
- Model B's accuracy is modest (0.633). It ranks risk; it does not predict rat populations.
- "Silent" means fewer complaints than expected for the risk and population, not zero complaints.

## Pipeline

| Step | File | What it does | Runtime |
|---|---|---|---|
| 1 | `01_build_cells.py` | inspections + 311 → every H3 r9 cell in NYC (7,633) × month; sweep flag; complaint dedupe | 7 s |
| 2 | `02_features.py` | 26 physical features per cell / cell-month (incl. binning), all lagged (no future data) | 15 s |
| 3 | `03_models.py` | Model A, A-variant, Model B ×5, Silence Score, uncertainty, spatial CV; `train_until(T)` hook | ~70 s |
| 4 | `04_optimizer.py` | N node sites: risk × data gap, ring-1 spacing, snapped to live street trees | 2 s |
| 5 | `05_backtest.py` | rolling backtest on sweeps, refit every 6 months | ~40 s |
| – | `validate_silence.py` | tests 1–4 above | ~60 s |
| – | `binning_effect.py` | before/after test of the Nov 2024 bin rule | ~20 s |
| 8 | `08_hotspots.py` | top 10 risk + top 10 silent hotspots, top-1% tiers (`--boroughs` to filter) | 1 s |
| 6 | `06_buildings.py` | top 5 buildings per silent block / node site (building-level Model B, `lots.py`) | ~15 s |
| – | `lot_model.py` | building- vs cell-level comparison (spatial CV) | ~50 s |
| – | `export.py` | `out/cells.json`, `out/plan.json` in the `web/src/types.ts` / `api/` contract | ~10 s |

```
cd Github/poc
python3 model/01_build_cells.py && python3 model/02_features.py && python3 model/03_models.py \
  && python3 model/04_optimizer.py && python3 model/05_backtest.py && python3 model/export.py
```

Raw data lives outside the repo in `../../data/raw/` (override with `DATA_DIR=...`); intermediates go to
`../../data/processed/`. Neither is committed. Sources and quirks: `data/DATA_DICTIONARY.md` in the project folder.

## Key decisions

- **Sweep = ≥10 Initial inspections on one tax block on one day** (73% of Initial inspections). Only 5.3% had a
  rat complaint on the lot in the prior year, vs 47.6% of single-lot visits. Agrees with the "no prior complaint
  on the lot" rule 72% of the time.
- **Model B** (LightGBM, cross-entropy): label = share of swept lots with rat activity per cell-month, weighted
  by lots swept. 26 physical features only: no complaint counts, no inspection counts, no HPD (tenant-triggered),
  no restaurant 04K/08A (held out as an independent check). `limited_english_share` is in neither model: it's the
  bias being measured. No IPW: training on sweeps already removes most complaint selection.
- **Model A** (LightGBM, Poisson): rat complaints per cell-month, all features + past complaints + HPD. The
  **A-variant** uses B's features only, so the Silence Score compares labels, not model capacity.
- **Silence** = pct(B) − pct(A-variant complaints **per resident**), per bootstrap copy. Silent = B in the top 40%,
  every copy agrees (interval excludes 0), gap > 25 points, and **≥100 homes** in the cell (people who could report;
  without this, empty industrial/park cells like Hunts Point or the Red Hook waterfront topped the list).
- **Uncertainty**: tree copies agree on unseen areas (false confidence), so a Beta-Binomial posterior (B = prior
  worth 20 lots, sweeps update it) plus `data_gap` = share of the estimate still a guess (1 = never swept).
- **Optimizer**: score = B × data_gap; cells where recent sweeps already found rats are skipped (known problems
  go to the DOHMH queue, not a sensor).
- **Complaint dedupe**: one East Harlem app user filed 5,339 complaints at one GPS point (up to 36/day, 1,306
  days). At most one complaint per exact spot per day counts (removes 5.9% of rows).

## Open items

- Fixed 16:20: `ci_b` came from the sweep-updated posterior, so `score_b` could sit outside its own interval
  (Bed-Stuy 0.035 vs [0.072, 0.106]). `ci_b` and `posterior` now describe `score_b` itself (Beta prior worth 20
  lots, widened to the bootstrap spread); 0 of 5,170 cells outside.

- `rmz` is null in `cells.json` until the Rat Mitigation Zone polygons are added.
- Stage demo cell `892a100d2c3ffff` (27th & 6th) is not silent in real data (silence −7.0). Pick a real one:
  in Manhattan, silent cells cluster in CD 106, 104 and 101; the LES (CD 103) is a known hotspot (high B *and* high A).

## Binning (DSNY containerization)

`share_binned` = share of a cell's lots that must use lidded bins that month. Each lot starts on the
earliest rule covering it: food businesses 2023-08-01, all businesses 2024-03-01, homes with 1–9 units
2024-11-12, 10+ unit buildings in Manhattan CD 9 (Empire Bins) by 2025-06. After Nov 2024, 73% of lots are
covered (DSNY: ~70% of trash). The official NYC Bin has been required since 2026-06-01 and enforced with fines
since 2026-09-08: same lots, too recent to measure. Adding it lifted Model B AUC 0.626 → 0.632.

Before/after (`binning_effect.py`, Dec–Oct 2023-24 vs 2024-25, Nov 2024 skipped):

| | complaints | rats found in sweeps |
|---|---|---|
| cells with many 1–9 unit homes (the rule's target) | −12% | −2% (4k lots swept) |
| cells with few small homes | −16% | −25% |

Complaints fell everywhere, so this can't show that bins cut rats (the groups differ: rarely swept Queens/SI
vs dense mitigation-zone areas). Suggestive only: where the rule applied, complaints fell 12% while inspectors
found rats at almost the same rate. Complaints may be falling faster than rats.
