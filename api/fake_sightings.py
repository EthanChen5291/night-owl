#!/usr/bin/env -S uv run --with pillow --with requests python
"""Stage fallback, plural: a batch of made-up sightings from owls spread over the city, so the sightings log and the
map have something to show before the real node fires. The crops are real frames of the rat prop from the team's own
recording session (one per scene, so lighting, floor, angle and zoom all vary), converted to grayscale like the node's
own output, with the labelled box drawn on.

  api/fake_sightings.py               POST api/fixtures/events.fake.json (fresh timestamps) to http://localhost:8000/event
  api/fake_sightings.py --write-only  only rewrite the fixture's timestamps
  api/fake_sightings.py --regen       rebuild the crops from the frames (git commit 0759071, string_review/rat) and the
                                      YOLO labels in $LABELS (default ~/div-hacks-26/vision/labels), then post
  API=http://192.168.7.1:8000 api/fake_sightings.py
Reset afterwards:  curl -X DELETE -H 'X-Demo-Reset: yes' http://localhost:8000/events
"""
from __future__ import annotations

import base64
import io
import json
import os
import random
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

HERE = Path(__file__).resolve().parent
OUT = HERE / "fixtures" / "events.fake.json"
API = os.environ.get("API", "http://localhost:8000")
FRAMES_COMMIT = "0759071"  # the reviewed rat frames, string_review/rat/<scene>_<n>.jpg
LABELS = Path(os.environ.get("LABELS", "~/div-hacks-26/vision/labels")).expanduser()
SCENES = ["bed_a", "bed_b", "bed_c", "clutter_h", "corr_d", "corr_f", "new_a", "new_b", "new_c", "new_d", "new_e", "r3_a", "r3_b", "stair_e", "stairtop_g", "new_f", "r3_c"]

# node id -> (h3 r9 cell, where, how many rat sightings)
NODES = [
    ("owl-eh-01", "892a1008d97ffff", "East Harlem, 2nd Ave & E 126th", 3),
    ("owl-sw-01", "892a100de33ffff", "South Williamsburg, Lee Ave", 2),
    ("owl-sw-02", "892a100de77ffff", "South Williamsburg, Bedford Ave", 1),
    ("owl-bx-01", "892a100a80bffff", "Concourse, E 167th", 2),
    ("owl-bx-02", "892a1001a6fffff", "Hunts Point", 1),
    ("owl-bk-01", "892a100ca7bffff", "Brownsville", 1),
    ("owl-bk-02", "892a10772abffff", "Sunset Park West", 1),
    ("owl-mn-01", "892a1072c37ffff", "Chinatown-Two Bridges", 1),
    ("owl-qn-01", "892a100c4afffff", "Corona", 1),
]


def frame_names() -> dict[str, list[str]]:
    """scene tag -> frame names in the reviewed set, from git (the frames were removed from the tree later)."""
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", FRAMES_COMMIT], cwd=HERE.parent, capture_output=True, text=True, check=True).stdout
    by_scene: dict[str, list[str]] = {}
    for line in out.splitlines():
        if line.startswith("string_review/rat/") and line.endswith(".jpg"):
            name = line.rsplit("/", 1)[1][:-4]
            by_scene.setdefault(name.rsplit("_", 1)[0], []).append(name)
    return by_scene


def prop_crop(rng: random.Random, name: str) -> tuple[str, list[float]]:
    """A grayscale thumbnail around the labelled rat in frame `name`, at a random zoom; returns (jpeg b64, bbox x y w h)."""
    raw = subprocess.run(["git", "show", f"{FRAMES_COMMIT}:string_review/rat/{name}.jpg"], cwd=HERE.parent, capture_output=True, check=True).stdout
    img = ImageOps.grayscale(Image.open(io.BytesIO(raw)))
    line = next(l for l in (LABELS / f"{name}.txt").read_text().splitlines() if l.startswith("0 "))
    cx, cy, bw, bh = (float(v) for v in line.split()[1:5])
    bbox = [round(cx - bw / 2, 3), round(cy - bh / 2, 3), round(bw, 3), round(bh, 3)]
    return thumbnail(rng, img, bbox), bbox


def thumbnail(rng: random.Random, img: Image.Image, bbox: list[float]) -> str:
    """The node's crop format: a 240x180 JPEG around `bbox` (x y w h, 0..1) at a random zoom, autocontrast, the box drawn on.
    `img` is grayscale for the node look (a colour image is kept in colour)."""
    w, h = img.size
    bw, bh = bbox[2], bbox[3]
    cx, cy = bbox[0] + bw / 2, bbox[1] + bh / 2
    zoom = rng.uniform(1.4, 3.2)  # how much context around the box: tight close-ups to wide views
    cw, ch = min(w, max(bw * w * zoom, 160)), min(h, max(bh * h * zoom, 120))
    cw, ch = (cw, cw * 0.75) if cw * 0.75 >= ch else (ch / 0.75, ch)  # 4:3
    cw, ch = min(cw, w), min(ch, h)
    x0 = min(max(0, cx * w - cw / 2 + rng.uniform(-0.15, 0.15) * cw), w - cw)
    y0 = min(max(0, cy * h - ch / 2 + rng.uniform(-0.15, 0.15) * ch), h - ch)
    crop = img.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((240, 180), Image.LANCZOS)
    crop = ImageOps.autocontrast(crop, cutoff=1).convert("RGB")
    sx, sy = 240 / cw, 180 / ch
    d = ImageDraw.Draw(crop)
    d.rectangle([(bbox[0] * w - x0) * sx, (bbox[1] * h - y0) * sy, ((bbox[0] + bw) * w - x0) * sx, ((bbox[1] + bh) * h - y0) * sy], outline=(255, 80, 60), width=2)
    buf = io.BytesIO()
    crop.save(buf, "JPEG", quality=72)
    return base64.b64encode(buf.getvalue()).decode()


def make_events(seed: int = 26) -> list[dict]:
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    by_scene = frame_names()
    scenes = iter(SCENES)
    events: list[dict] = []
    for node_id, h3, _where, n in NODES:
        for _ in range(n):
            scene = next(scenes)
            names = by_scene[scene]
            crop_b64, bbox = prop_crop(rng, names[len(names) // 2])
            ts = now - timedelta(hours=rng.uniform(0.3, 40))
            ts = ts.replace(hour=rng.choice([21, 22, 23, 0, 1, 2, 3, 4]))  # rats work nights
            if ts > now:
                ts -= timedelta(days=1)
            events.append({
                "node_id": node_id, "h3": h3, "ts": ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "class": "rat",
                "conf": round(rng.uniform(0.62, 0.97), 2), "n_hits": rng.randint(3, 9), "bbox": bbox,
                "crop_b64": crop_b64, "fw": "0.1.0",
            })
    # one person walking past a Brownsville owl: the classifier's other class, kept out of the posterior by the API
    events.append({
        "node_id": "owl-bk-01", "h3": "892a100ca7bffff", "ts": (now - timedelta(hours=5.4)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "class": "person", "conf": 0.88, "n_hits": 2, "bbox": [0.4, 0.1, 0.25, 0.8], "crop_b64": "", "fw": "0.1.0",
    })
    events.sort(key=lambda e: e["ts"])
    return events


def restamp(events: list[dict]) -> list[dict]:
    """Shift the batch so its newest event is a few minutes ago, keeping the gaps between events."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    parse = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=timezone.utc)
    newest = max(parse(e["ts"]) for e in events)
    shift = now - timedelta(minutes=4) - newest
    for e in events:
        e["ts"] = (parse(e["ts"]) + shift).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return events


def main() -> None:
    if "--regen" in sys.argv or not OUT.is_file():
        events = make_events()
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
        print(f"{e['ts']} {e['node_id']:10s} {e['class']:6s} conf={e['conf']:.2f} hits={e['n_hits']} -> score_b {body.get('score_b_updated')}", file=sys.stderr)


if __name__ == "__main__":
    main()
