"""Shared paths and constants for the node-location model."""
import os
from pathlib import Path

# Data lives outside the repo (never committed). Override with DATA_DIR=...
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[3] / "data"))
RAW = DATA_DIR / "raw"
PROCESSED = DATA_DIR / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)

H3_RES = 9
START_DATE = "2010-01-01"

# Tax block with at least this many Initial inspections on one day = a sweep.
# 2025 distribution is bimodal: ~20k single-lot block-days vs ~4k with 10+.
SWEEP_MIN_LOTS = 10

# Rough NYC bounding box, drops 0/garbage coordinates.
NYC_LAT = (40.49, 40.92)
NYC_LNG = (-74.27, -73.68)

# 311 descriptors counted as rat complaints (mouse sightings excluded).
RAT_DESCRIPTORS = ("Rat Sighting", "Signs of Rodents", "Condition Attracting Rodents")
