#!/usr/bin/env -S uv run --with pillow --with requests python
"""Stage fallback with real animals: sightings whose crops are real photographs of wild rats and house mice in the kinds of
light a node meets (daylight, low sun, dusk, indoor gloom, flash at night, unlit subway track), cut to the node's own crop
format. The photos are openly licensed from Wikimedia Commons; credits in fixtures/rodents.credits.json (CC BY needs them
on the "What's real" slide if a crop is shown on stage). The events are fake: node ids and cells from fake_sightings.NODES.

  api/real_sightings.py               POST fixtures/events.real.json (fresh timestamps) to http://localhost:8000/event
  api/real_sightings.py --write-only  only rewrite the fixture's timestamps
  api/real_sightings.py --regen       rebuild the crops from fixtures/rodents/*.jpg (downloaded with --fetch), then post
  api/real_sightings.py --fetch       download the photos from Commons into fixtures/rodents/ (gitignored), then --regen
  api/real_sightings.py --colour      with --regen: keep the photos in colour instead of the node's grayscale
Reset afterwards:  curl -X DELETE -H 'X-Demo-Reset: yes' http://localhost:8000/events
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageOps

from fake_sightings import NODES, restamp, thumbnail

HERE = Path(__file__).resolve().parent
OUT = HERE / "fixtures" / "events.real.json"
CREDITS = HERE / "fixtures" / "rodents.credits.json"
PHOTOS = HERE / "fixtures" / "rodents"
API = os.environ.get("API", "http://localhost:8000")
UA = {"User-Agent": "NightOwl-hackathon/0.1 (DivHacks 2026 demo)"}

# Commons file title, the animal's box in the frame (x y w h, 0..1), and the light it was seen in
PHOTOS_LIST: list[tuple[str, list[float], str]] = [
    ("Hey rat, mind the gap! (126268968).jpg", [0.40, 0.47, 0.21, 0.27], "subway platform at night"),
    ("NYC Subway rat.jpg", [0.44, 0.44, 0.17, 0.14], "unlit track bed"),
    ("Rat in NYC subway.jpg", [0.47, 0.56, 0.11, 0.14], "flash over dark track"),
    ("Rats eating subway trash 2010-07-27.jpg", [0.31, 0.49, 0.13, 0.16], "near-dark track"),
    ("Rat in NYC subway 2.jpg", [0.63, 0.53, 0.15, 0.18], "flash, track from the platform edge"),
    ("2026-04-16 22 40 41 Disoriented, lethargic deer mouse (likely due to ingesting rodenticide) on a driveway at night along Aquetong Lane in the Mountainview section of Ewing Township, Mercer County, New Jersey.jpg", [0.42, 0.16, 0.26, 0.31], "phone flash on a driveway at night"),
    ("Mus musculus 57127864.jpg", [0.25, 0.28, 0.50, 0.45], "torch beam on carpet"),
    ("Rattus Norvegicus 03-17-2013.jpg", [0.28, 0.25, 0.62, 0.45], "flash on a dark floor"),
    ("White-footed Mouse, 2016-03-08-11.46.jpg", [0.00, 0.05, 1.00, 0.90], "studio flash, black background"),
    ("2010-365-5 My Stunned House Mate (4250313594).jpg", [0.23, 0.14, 0.72, 0.80], "daylight on soil"),
    ("Brown rat brighton.jpg", [0.42, 0.18, 0.40, 0.55], "daylight in the shade of a wall"),
    ("Brown Rat (Rattus norvegicus) also called Norway Rat or Common Rat - Mathias Baldwin Park, Philadelphia, Pennsylvania, USA.jpg", [0.19, 0.11, 0.40, 0.60], "soft daylight, climbing a stone wall"),
    ("Brown rat (Rattus norvegicus) Drenthe 2.jpg", [0.05, 0.28, 0.72, 0.30], "low golden sun, water"),
    ("London Scruffy Rat.jpg", [0.05, 0.12, 0.85, 0.85], "overcast dusk, stone"),
    ("Rattus norvegicus - Brown rat 01.jpg", [0.28, 0.20, 0.55, 0.70], "daylight in a garden"),
    ("Dark Brown Rat.JPG", [0.31, 0.49, 0.42, 0.22], "indoor gloom on a sofa"),
    ("House mouse (Mus musculus) 2732.jpg", [0.05, 0.22, 0.85, 0.55], "daylight, top-down on concrete"),
]


def slug_of(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower())[:60].strip("-")


def fetch() -> None:
    """Download each photo at 900 px plus its licence and author, from the Commons API."""
    PHOTOS.mkdir(parents=True, exist_ok=True)
    credits: dict[str, dict] = json.loads(CREDITS.read_text()) if CREDITS.is_file() else {}
    titles = [t for t, _, _ in PHOTOS_LIST]
    for i in range(0, len(titles), 10):
        params = dict(action="query", titles="|".join("File:" + t for t in titles[i:i + 10]), prop="imageinfo",
                      iiprop="url|extmetadata", iiurlwidth=900, format="json")
        url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
        pages = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())["query"]["pages"]
        for p in pages.values():
            if "imageinfo" not in p:
                print(f"missing on Commons: {p.get('title')}", file=sys.stderr)
                continue
            ii = p["imageinfo"][0]
            meta = ii["extmetadata"]
            title = p["title"].removeprefix("File:")
            slug = slug_of(title)
            data = urllib.request.urlopen(urllib.request.Request(ii["thumburl"], headers=UA), timeout=60).read()
            (PHOTOS / f"{slug}.jpg").write_bytes(data)
            credits[slug] = {
                "title": title,
                "author": re.sub("<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip(),
                "license": meta.get("LicenseShortName", {}).get("value"),
                "url": ii["descriptionurl"],
            }
            print(f"fetched {slug} ({credits[slug]['license']})", file=sys.stderr)
    CREDITS.write_text(json.dumps(credits, indent=1, ensure_ascii=False))


def make_events(seed: int = 27, colour: bool = False) -> list[dict]:
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    nodes = [n for n in NODES for _ in range(2)]  # two sightings per owl, round robin
    events: list[dict] = []
    for i, (title, bbox, light) in enumerate(PHOTOS_LIST):
        path = PHOTOS / f"{slug_of(title)}.jpg"
        if not path.is_file():
            sys.exit(f"{path} is missing: run with --fetch first")
        img = Image.open(path)
        img = ImageOps.exif_transpose(img).convert("RGB")
        if not colour:
            img = ImageOps.grayscale(img)
        node_id, h3, _where, _n = nodes[i % len(nodes)]
        ts = now - timedelta(hours=rng.uniform(0.2, 46))
        ts = ts.replace(hour=rng.choice([20, 21, 22, 23, 0, 1, 2, 3, 4, 5]))  # rats work nights
        if ts > now:
            ts -= timedelta(days=1)
        events.append({
            "node_id": node_id, "h3": h3, "ts": ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "class": "rat",
            "conf": round(rng.uniform(0.58, 0.97), 2), "n_hits": rng.randint(3, 9), "bbox": bbox,
            "crop_b64": thumbnail(rng, img, bbox), "fw": "0.1.0",
        })
        print(f"{node_id:10s} {light:36s} <- {title[:60]}", file=sys.stderr)
    events.sort(key=lambda e: e["ts"])
    return events


def main() -> None:
    if "--fetch" in sys.argv:
        fetch()
    if "--fetch" in sys.argv or "--regen" in sys.argv or not OUT.is_file():
        events = make_events(colour="--colour" in sys.argv)
    else:
        events = restamp(json.loads(OUT.read_text()))
    OUT.write_text(json.dumps(events, indent=1))
    print(f"wrote {len(events)} events -> {OUT}", file=sys.stderr)
    if "--write-only" in sys.argv:
        return
    import requests

    for e in events:
        r = requests.post(f"{API}/event", json=e, timeout=5)
        r.raise_for_status()
        body = r.json()
        print(f"{e['ts']} {e['node_id']:10s} conf={e['conf']:.2f} hits={e['n_hits']} -> score_b {body.get('score_b_updated')}", file=sys.stderr)


if __name__ == "__main__":
    main()
