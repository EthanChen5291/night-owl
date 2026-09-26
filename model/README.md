# model/ — where are the rats nobody reports?

Sanjavan's node-location pipeline for Barn Owl. Written on 2026-09-26 (event day). Last updated **Sat 13:30**.

## Headline results

| Claim | Number | Where |
|---|---|---|
| **Backtest: our picks beat "go where people complain"** | **21.9% vs 17.2%** of swept lots had rats (+27%), won **76 of 83 months** (2019-01 → 2026-08) | `out/backtest.json` |
| Backtest: beats "go where rats were found before" | 21.9% vs 19.4%, won 68 of 83 months, without using inspection history | `out/backtest.json` |
| **Backtest: quiet blocks only** | **17.9% vs 10.3% random (1.7×), won 81 of 83 months** | `out/backtest.json` |
| Quiet ≠ rat-free | loudest vs quietest areas: complaints differ **17.8×**, rats found in sweeps only **2.3×** | `out/validation.json` test 1 |
| Out-of-time check | trained to 2023-12; quiet cells swept in 2024: high-risk third 20.1% vs low-risk third 7.8% | test 2 |
| No ground truth where nobody complains | **97%** of the quietest-quartile cells had no proactive sweep in 24 months, vs 55% of the loudest | `03_models.py` data_gap |
| Silent blocks (high B, low A) | **501 cells**, median income **$75k vs $92k**, limited-English households 12.7% vs 9.2% | `out/cells.json` (`is_silent`) |
| Sensor picks | 20 sites on real tree pits, 95% never swept, median income $61k | `out/plan.json` |
| Model B accuracy | AUC **0.626** on held-out community districts (logistic baseline 0.561) | `out/metrics.json` |

Backtests are scored **only on cells DOHMH actually swept that month**. Silent blocks are rarely
inspected, so scoring on "any inspection found rats" grades the model on where DOHMH goes, not where rats are.

## Honest limits (say these before a judge does)

- **Never-swept areas can't be validated with existing data.** We tried restaurant rat violations (04K) as an
  independent check there: no clear signal (2.3% / 2.9% / 2.8% by risk tier, z≈1.2). Not claimed. That gap is
  what the nodes are for.
- **The equity result depends on how Model A is normalised.** Per resident (used, because complaints come from
  people): silent blocks $74k / 12.7% limited-English. Raw counts: ~average. Per property: richer. Table in
  `out/validation.json` test 4.
- Model B's accuracy is modest (0.63). It ranks risk; it does not predict rat populations.
- "Silent" means fewer complaints than expected for the risk and population, not zero complaints.

## Pipeline

| Step | File | What it does | Runtime |
|---|---|---|---|
| 1 | `01_build_cells.py` | inspections + 311 → every H3 r9 cell in NYC (7,633) × month; sweep flag; complaint dedupe | 7 s |
| 2 | `02_features.py` | 25 physical features per cell / cell-month, all lagged (no future data) | 10 s |
| 3 | `03_models.py` | Model A, A-variant, Model B ×5, Silence Score, uncertainty, spatial CV; `train_until(T)` hook | ~70 s |
| 4 | `04_optimizer.py` | N node sites: risk × data gap, ring-1 spacing, snapped to live street trees | 2 s |
| 5 | `05_backtest.py` | rolling backtest on sweeps, refit every 6 months | ~40 s |
| – | `validate_silence.py` | tests 1–4 above | ~60 s |
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
  by lots swept. 25 physical features only: no complaint counts, no inspection counts, no HPD (tenant-triggered),
  no restaurant 04K/08A (held out as an independent check). `limited_english_share` is in neither model: it's the
  bias being measured. No IPW: training on sweeps already removes most complaint selection.
- **Model A** (LightGBM, Poisson): rat complaints per cell-month, all features + past complaints + HPD. The
  **A-variant** uses B's features only, so the Silence Score compares labels, not model capacity.
- **Silence** = pct(B) − pct(A-variant complaints **per resident**), per bootstrap copy. Silent = B in the top 40%,
  every copy agrees (interval excludes 0), gap > 25 points.
- **Uncertainty**: tree copies agree on unseen areas (false confidence), so a Beta-Binomial posterior (B = prior
  worth 20 lots, sweeps update it) plus `data_gap` = share of the estimate still a guess (1 = never swept).
- **Optimizer**: score = B × data_gap; cells where recent sweeps already found rats are skipped (known problems
  go to the DOHMH queue, not a sensor).
- **Complaint dedupe**: one East Harlem app user filed 5,339 complaints at one GPS point (up to 36/day, 1,306
  days). At most one complaint per exact spot per day counts (removes 5.9% of rows).

## Open items

- `rmz` is null in `cells.json` until the Rat Mitigation Zone polygons are added.
- Stage demo cell `892a100d2c3ffff` (27th & 6th) is not silent in real data (silence −1.2). Pick a real one:
  in Manhattan, silent cells cluster in CD 106, 104 and 101; the LES (CD 103) is a known hotspot (high B *and* high A).
- Binning (containerization) feature: small homes have used lidded bins since 2024-11-12; the official NYC Bin has been
  enforced since 2026-09-08. Planned as a time-varying feature.
