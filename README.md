<div align="center">

# NightOwl

**NYC's automated rat surveillance system**

[![Site](https://img.shields.io/badge/site-barn--owl.tech-blue.svg)](https://barn-owl.tech)
[![Pitch](https://img.shields.io/badge/pitch-deck-green.svg)](pitch/README.md)
[![Handoff](https://img.shields.io/badge/docs-technical%20handoff-orange.svg)](docs/utsav-technical-handoff.md)
[![Evidence](https://img.shields.io/badge/evidence-limitations-lightgrey.svg)](#limitations)


</div>

![NightOwl map of Manhattan](docs/media/map-manhattan.jpg)

## Overview

NYC estimates about 3 million rats and runs ~152,000 initial rodent inspections a year, targeted mostly by 311 complaints. Yet these inspections focus on the callees rather than actual rat populations themselves -> the richest fifth of blocks files 76% more complaints per rat found than the poorest fifth, which has 51% more infestations.

NightOwl scores every block-sized cell in the city each month, flags the blocks that are likely ratty but quiet, and places a low-cost camera node, an **Owl**, where the model is least certain. Owl sightings flow back into the map and rerank the next placements.

## How it works

<table>
  <tr>
    <td width="50%" align="center"><img src="docs/media/model-a.png" alt="Model A: 311 complaints, pest history, and violations"></td>
    <td width="50%" align="center"><img src="docs/media/model-b.png" alt="Model B: rat inspections, environment, buildings, and food"></td>
  </tr>
  <tr>
    <td colspan="2" align="center"><img src="docs/media/owl-loop.png" width="46%" alt="The Owl loop: placement model, PIR trigger, camera and classifier, server and map"></td>
  </tr>
</table>

## Results

Rolling backtest, 119 months (2016-01 → 2026-08), top 50 cells scored on lots the city swept that month:

| Picking strategy | Swept lots with rat signs |
|---|---:|
| **Model B** | **19.5%** (best in 108 / 119 months) |
| Most 311 complaints | 15.2% |
| Rats found before | 17.1% |
| Quiet blocks: Model B vs random | **15.6% vs 8.8%** (117 / 119 months) |

## Owl node

<p align="center"><img src="docs/media/owl-node.jpg" width="320" alt="As-built Owl node"></p>

Raspberry Pi 5, IMX219 NoIR camera, 850 nm IR illuminator, HC-SR501 PIR, PiSugar battery, printed enclosure ([build files](model/enclosure/README.md)). The PIR wakes the camera on motion and heat; a YOLO11n detector fine-tuned on reviewed footage decides on-device. Only the event (timestamp, cell, confidence, small crop) goes to the local API. No video is stored or uploaded!

![Detector frames: rat box steady, passing person boxed separately](docs/media/detector-frames.jpg)

## Dashboards

`/dashboards` turns a question into validated charts through a Grok tool loop over seven datasets: the model month, sites, backtest, Owl events, and 16 years of NYC Open Data complaints and inspections by borough, ZIP area and ACS income band. Every chart names its source.

## Installation

```sh
cp .env.example .env          # add XAI_API_KEY for the dashboard assistant
pnpm --dir web install --frozen-lockfile
```

## Quick start

```sh
./api/run.sh                  # API on :8000 (restart after editing api/)
pnpm --dir web dev            # map on http://localhost:5173
```

Without the API the map shows labeled fixture data. Refresh the open-data history with `./data/fetch_history.py`. Checks:

```sh
uv run --project api pytest -q api/tests
pnpm --dir web build && pnpm --dir web lint
```

## Limitations

- The detector was trained on a room-lit plush rat. Infrared footage and wild rats are untested. Its fresh box test scored 0.616 rat AP50 ([fresh test](vision/V5_FRESH_RESULTS.md), [event test](vision/V5_FORMAL_EVENT_RESULTS.md)).

## Repository

| Path | Contents |
|---|---|
| [web/](web/README.md) | React + three.js map, dashboards UI |
| [api/](api/README.md) | FastAPI, event store, posterior updates, dashboard tool loop |
| [model/](model/README.md) | Cell features, Models A/B, planner, backtest, enclosure |
| [data/](data/README.md) | Open-data bake and dashboard history fetch |
| [vision/](vision/RUNBOOK.md) | Detector training, evaluation, Pi runtime |
| [city/](city/README.md) | H3 fixtures and 3D city bake |
| [pitch/](pitch/README.md) | Deck, script, evidence receipts |

## Acknowledgements

NYC Open Data (311, DOHMH rodent inspections, PLUTO, DSNY, DOB), US Census ACS, NOAA, [H3](https://h3geo.org), [LightGBM](https://github.com/microsoft/LightGBM), [Ultralytics YOLO11](https://github.com/ultralytics/ultralytics), [three.js](https://threejs.org). The project was previously named Barn Owl; that name survives only in Pi paths and the `barn-owl.tech` domain.
