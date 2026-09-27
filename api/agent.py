"""NightOwl assistant: Grok (xAI) with tools over the model output, the Pi node and the map.

POST /agent/chat streams Server-Sent Events back to the web app's chat panel:
    {"type": "tool", "id", "name", "label", "state": "start" | "done", "summary"?}   a tool ran on the server
    {"type": "image", "src", "caption"}                                               show a picture in the chat
    {"type": "thinking", "state": "start" | "done"}                                    Grok is reasoning before it answers
    {"type": "delta", "text"}                                                          answer text, as it streams
    {"type": "client_tools", "calls": [{"id", "name", "args"}]}                        run these in the browser, then POST again
    {"type": "messages", "messages"}                                                   the history to send next time
    {"type": "error", "text"} / {"type": "done"}

The browser keeps the conversation (no server state). Server tools read model/out/*.json through the Store and
the Pi node through the barn-owl dashboard on 127.0.0.1 (a read-only agent token). Browser tools
(CLIENT_TOOLS) see what only the page knows: the placed owls, the camera view, a screenshot of the map.
Standard library only, so the API keeps its three dependencies.

Env: XAI_API_KEY (required), XAI_MODEL (default grok-4.7), NIGHT_OWL_DASH_URL (default http://127.0.0.1:8771),
AGENT_TOKEN (the dashboard's read token).
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from store import Store

XAI_URL = "https://api.x.ai/v1/chat/completions"
MODEL = os.environ.get("XAI_MODEL", "grok-4.7")
REASONING = os.environ.get("XAI_REASONING", "low")  # grok-4.7 thinks ~2x faster at "low" and answers as well here
DASH = os.environ.get("NIGHT_OWL_DASH_URL", os.environ.get("BARN_OWL_DASH_URL", "http://127.0.0.1:8771")).rstrip("/")
GEOSEARCH = "https://geosearch.planninglabs.nyc/v2/autocomplete"
API_DIR = Path(__file__).resolve().parent

MAX_ROUNDS = 6            # tool rounds per question
MAX_TOKENS = 1600
MAX_HISTORY = 40          # messages kept from the browser
MAX_MSG_CHARS = 12_000
MAX_IMAGE_B64 = 2_500_000  # a map screenshot, as a data URL
RATE_PER_MIN, RATE_PER_DAY = 15, 300

Emit = Callable[[dict], Awaitable[None]]


# ---------------------------------------------------------------------------------------------- prompt

def system_prompt() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""You are the NightOwl assistant, built into the NightOwl map (DivHacks 2026, track: Hack the City). Now: {now}.

What NightOwl is: NYC's rat map is built from 311 calls, so it is a map of who complains. NightOwl scores every H3
resolution-9 hexagon (~0.1 km²) in NYC with two models:
- Model A, "what the city sees": predicted 311 rat complaints (complaints_pct is its citywide percentile).
- Model B, "what's actually there": P(active rat signs | a proactive Health Dept inspection), from physical and
  environmental features only (rat_risk_pct is its percentile, p_active_rat_signs the probability).
- Silence = rat_risk_pct - complaints_pct. A "silent block" has high B and low A: rats nobody reports.
- A backtest on real inspections validates it. "Owls" are small Pi 5 camera nodes (NoIR camera + 850 nm IR light
  + PIR motion sensor) mounted on street-tree guards; each detection updates that hexagon's Beta-Binomial
  posterior (live_detections). The team's physical node is "the Pi" (pi_* tools): live status, motion activity
  logged in Tiger Data (TimescaleDB), recordings in MongoDB, camera frames.
- The web app: a 3D map of NYC by borough, a mode toggle (what the city sees / what's there / silence), the Owls
  panel (placed nodes and suggested sites), a sightings log, and the backtest chart.

How to work:
- Use the tools for every number; never invent data. Say which borough and neighbourhood a hexagon is in.
- Find places with geocode, then search_cells near the point. Rank with search_cells.
- Show the map when it helps (screenshot_map), and camera frames when asked about the node (camera_image).
- Be brief: a sentence or two, then a short list or small table. Markdown is rendered. Round sensibly.
- The map screenshot shows the user's current view; get_app_state says which borough and mode that is.
- You can drive the user's map: fly_to a place (after geocode or a hexagon lookup), set_map_mode, enter_borough,
  show_panel (owls / logs / backtest), select_owl, show_suggested_site, set_lighting. When you talk about a specific
  place, take the user there (one fly_to to the most relevant spot) unless they said not to. Pick the mode that
  matches the question (silent blocks -> silence, rat risk -> b, complaints -> a). Don't bounce the camera around:
  one or two moves per answer. Say briefly what you did ("I've flown you to ...").
"""


# ---------------------------------------------------------------------------------------------- helpers

def _http_json(url: str, *, headers: dict | None = None, timeout: float = 15) -> Any:
    req = urllib.request.Request(url, headers={"accept": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _http_bytes(url: str, *, headers: dict | None = None, timeout: float = 15) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=timeout) as r:
        return r.read()


def _dash(path: str) -> Any:
    token = os.environ.get("AGENT_TOKEN", "")
    if not token:
        raise RuntimeError("the node dashboard is not connected (no AGENT_TOKEN on the server)")
    return _http_json(DASH + path, headers={"x-agent-token": token})


def _dash_bytes(path: str) -> bytes:
    return _http_bytes(DASH + path, headers={"x-agent-token": os.environ.get("AGENT_TOKEN", "")})


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12_742_000 * math.asin(math.sqrt(a))


def _ago(ms: float | None) -> str | None:
    if not ms:
        return None
    s = max(0, time.time() - ms / 1000)
    return f"{int(s)} s ago" if s < 90 else f"{int(s // 60)} min ago" if s < 5400 else f"{s / 3600:.1f} h ago"


class Data:
    """Model output, loaded through the Store (so /cells' live posterior overlay applies) plus cell centres."""

    def __init__(self, store: Store, month: str | None = None, plan_k: int | None = None):
        self.store = store
        self.month = month
        self.plan_k = plan_k
        self._centres: dict[str, list[float]] | None = None

    def centres(self) -> dict[str, list[float]]:
        if self._centres is None:
            try:
                self._centres = json.loads((API_DIR / "cell_centres.json").read_text())
            except FileNotFoundError:
                self._centres = {}
        return self._centres

    def cells(self) -> tuple[str, list[dict]]:
        data, _ = self.store.cells(self.month)
        return data.get("month", "?"), data.get("cells", [])

    def model_file(self, name: str) -> dict:
        path = self.store.data_dir / "model" / "out" / name
        return json.loads(path.read_text()) if path.exists() else {}

    def row(self, c: dict) -> dict:
        ll = self.centres().get(c["h3"])
        post = c.get("posterior") or {}
        return {
            "h3": c["h3"], "neighborhood": c.get("neighborhood"), "borough": c.get("borough"),
            "lat": ll[0] if ll else None, "lon": ll[1] if ll else None,
            "rat_risk_pct": c.get("pct_b"), "complaints_pct": c.get("pct_a"), "silence": c.get("silence"),
            "p_active_rat_signs": round(c.get("score_b", 0), 4), "silent_block": c.get("is_silent"),
            "complaints_12m": c.get("n_complaints_12m"), "rank_risk": c.get("rank_risk"), "rank_silent": c.get("rank_silent"),
            "live_detections": post.get("n_events", 0),
            "posterior_mean": round(post["alpha"] / (post["alpha"] + post["beta"]), 4) if post.get("alpha") else None,
        }


# ---------------------------------------------------------------------------------------------- server tools

SORTS = {"rat_risk": "pct_b", "silence": "silence", "complaints": "pct_a", "live_detections": None}


def t_city_overview(d: Data, a: dict) -> tuple[Any, list]:
    month, cells = d.cells()
    boroughs: dict[str, dict] = defaultdict(lambda: {"hexagons": 0, "silent_blocks": 0, "risk_sum": 0.0, "complaints_12m": 0})
    for c in cells:
        b = boroughs[c.get("borough") or "unknown"]
        b["hexagons"] += 1
        b["silent_blocks"] += 1 if c.get("is_silent") else 0
        b["risk_sum"] += c.get("score_b", 0)
        b["complaints_12m"] += c.get("n_complaints_12m") or 0
    by_b = {k: {"hexagons": v["hexagons"], "silent_blocks": v["silent_blocks"], "complaints_12m": v["complaints_12m"],
                "mean_p_active_rat_signs": round(v["risk_sum"] / v["hexagons"], 4)} for k, v in boroughs.items()}
    def top(sort_key: str) -> list[dict]:
        ranked = sorted(cells, key=lambda c: float(c.get(sort_key) or 0), reverse=True)[:8]
        return [{"rank": rank, "neighborhood": c.get("neighborhood"), "borough": c.get("borough"),
                 "h3": c["h3"], "lat": (d.centres().get(c["h3"]) or [None, None])[0],
                 "lon": (d.centres().get(c["h3"]) or [None, None])[1],
                 "rat_risk": c.get("score_b"), "silence": c.get("silence")}
                for rank, c in enumerate(ranked, 1)]
    return {"month": month, "hexagons": len(cells), "by_borough": by_b,
            "top_rat_risk": top("score_b"), "top_silent_blocks": top("silence")}, []


def t_search_cells(d: Data, a: dict) -> tuple[Any, list]:
    month, cells = d.cells()
    borough = (a.get("borough") or "").lower().strip()
    hood = (a.get("neighborhood") or "").lower().strip()
    sort = a.get("sort_by") or "rat_risk"
    limit = max(1, min(int(a.get("limit") or 10), 25))
    lat, lon = a.get("near_lat"), a.get("near_lon")
    radius = float(a.get("radius_m") or 800)
    rows = []
    for c in cells:
        if borough and borough not in (c.get("borough") or "").lower():
            continue
        if hood and hood not in (c.get("neighborhood") or "").lower():
            continue
        r = d.row(c)
        if lat is not None and lon is not None:
            if r["lat"] is None:
                continue
            r["distance_m"] = round(_haversine_m(float(lat), float(lon), r["lat"], r["lon"]))
            if r["distance_m"] > radius:
                continue
        rows.append(r)
    key = SORTS.get(sort, "pct_b")
    if sort == "live_detections":
        rows.sort(key=lambda r: -(r["live_detections"] or 0))
    elif sort == "nearest" and lat is not None:
        rows.sort(key=lambda r: r.get("distance_m", 0))
    else:
        field = {"pct_b": "rat_risk_pct", "silence": "silence", "pct_a": "complaints_pct"}[key]
        rows.sort(key=lambda r: -(r[field] if r[field] is not None else -1e9))
    return {"month": month, "matched": len(rows), "sort_by": sort, "results": rows[:limit]}, []


def t_get_cell(d: Data, a: dict) -> tuple[Any, list]:
    month, cells = d.cells()
    by = {c["h3"]: c for c in cells}
    h3 = (a.get("h3") or "").lower().strip()
    if not h3 and a.get("lat") is not None and a.get("lon") is not None:
        lat, lon = float(a["lat"]), float(a["lon"])
        best = min(d.centres().items(), key=lambda kv: _haversine_m(lat, lon, kv[1][0], kv[1][1]), default=None)
        if best and _haversine_m(lat, lon, best[1][0], best[1][1]) < 350:
            h3 = best[0]
    c = by.get(h3)
    if not c:
        return {"error": "no modelled hexagon there (outside NYC's modelled area, or water/park)"}, []
    out = d.row(c)
    out["month"] = month
    out["top_reasons"] = c.get("reasons", [])
    out["ci_p_active_rat_signs"] = c.get("ci_b")
    out["inspections"] = c.get("n_inspections")
    out["community_district"] = c.get("cd")
    buildings = d.model_file("buildings.json")
    blds = buildings.get("cells", {}).get(h3) if buildings.get("month") == month else None
    if blds:
        out["riskiest_buildings"] = blds[:5]
    placements = d.model_file("placements.json")
    spots = placements.get("cells", {}).get(h3) if placements.get("month") == month else None
    if spots:
        out["owl_mount_spots"] = [{k: s.get(k) for k in ("rank", "mount_address", "lat", "lon", "score", "reasons")} for s in spots[:3]]
    return out, []


def t_geocode(d: Data, a: dict) -> tuple[Any, list]:
    q = (a.get("query") or "").strip()
    if not q:
        return {"error": "empty query"}, []
    data = _http_json(GEOSEARCH + "?" + urllib.parse.urlencode({"text": q, "size": 5}))
    out = []
    for f in data.get("features", [])[:5]:
        p = f.get("properties", {})
        lon, lat = f.get("geometry", {}).get("coordinates", [None, None])
        out.append({"label": p.get("label"), "borough": p.get("borough"), "neighbourhood": p.get("neighbourhood"), "lat": lat, "lon": lon})
    return {"results": out}, []


def t_node_sites(d: Data, a: dict) -> tuple[Any, list]:
    plan, _ = d.store.plan(d.month, d.plan_k)
    _, cells = d.cells()
    by = {c["h3"]: c for c in cells}
    placements = d.model_file("placements.json")
    spots = placements.get("cells", {}) if placements.get("month") == plan.get("month") else {}
    borough = (a.get("borough") or "").lower().strip()
    limit = max(1, min(int(a.get("limit") or 8), 20))
    out = []
    for n in plan.get("nodes", []):
        c = by.get(n["h3"], {})
        if borough and borough not in (c.get("borough") or "").lower():
            continue
        s = spots.get(n["h3"], [])
        out.append({"rank": n["rank"], "h3": n["h3"], "neighborhood": c.get("neighborhood"), "borough": c.get("borough"),
                    "lat": n["lat"], "lon": n["lon"], "expected_gain": n.get("expected_gain"), "silence": n.get("silence"),
                    "why": n.get("reason"), "best_mount": s[0].get("mount_address") if s else None})
        if len(out) >= limit:
            break
    return {"month": plan.get("month"), "requested_month": plan.get("requested_month"),
            "source": plan.get("source"), "replanned": plan.get("replanned"), "sites": out}, []


def t_model_quality(d: Data, a: dict) -> tuple[Any, list]:
    bt = d.model_file("backtest.json").get("summary", {})
    return {"backtest_summary": bt, "metrics": d.model_file("metrics.json"), "owl_spot_validation": d.model_file("placements_validation.json"),
            "lot_model": {k: v for k, v in d.model_file("lot_model_metrics.json").items() if k != "top_features_lot_model"}}, []


def t_recent_sightings(d: Data, a: dict) -> tuple[Any, list]:
    limit = max(1, min(int(a.get("limit") or 10), 30))
    events = d.store.queue(limit)
    imgs = []
    if a.get("with_images"):
        for e in events[:3]:
            if e.get("crop_b64"):
                src = e["crop_b64"] if e["crop_b64"].startswith("data:") else "data:image/jpeg;base64," + e["crop_b64"]
                imgs.append({"src": src, "caption": f"{e.get('class')} {round(e.get('conf', 0) * 100)}% · {e.get('node_id')} · {e.get('ts')}"})
    slim = [{k: v for k, v in e.items() if k != "crop_b64"} for e in events]
    return {"events": slim, "count": len(slim)}, imgs


def t_pi_status(d: Data, a: dict) -> tuple[Any, list]:
    s = _dash("/api/state?live=0")
    st = s.get("state") or {}
    return {"online": s.get("online"), "last_check_in": _ago(st.get("ts")), "motion_now": st.get("pir"),
            "last_motion": _ago(st.get("lastMotion")), "ir_light_on": st.get("ir"), "cpu_temp_c": st.get("cpuTemp"),
            "wifi_dbm": st.get("wifiDbm"), "host": st.get("host"), "zoom": s.get("zoom"),
            "recording_now": s.get("recording")}, []


def t_pi_activity(d: Data, a: dict) -> tuple[Any, list]:
    rng = int(a.get("range_minutes") or 60)
    rng = min((15, 60, 360, 1440, 10080), key=lambda r: abs(r - rng))
    act = _dash(f"/api/activity?range={rng}")
    for k in ("series", "detections"):
        if isinstance(act.get(k), list) and len(act[k]) > 60:  # keep the tool result small: every nth point
            step = math.ceil(len(act[k]) / 60)
            act[k] = act[k][::step]
    return act, []


def t_pi_recordings(d: Data, a: dict) -> tuple[Any, list]:
    limit = max(1, min(int(a.get("limit") or 10), 30))
    r = _dash("/api/recordings")
    recs = [{"id": str(x.get("_id")), "started": x.get("startedAt"), "ended": x.get("endedAt"), "seconds": x.get("durationSec"),
             "preview_frames": x.get("frames"), "status": x.get("status"), "zoom": x.get("zoom"),
             "pi_15fps_frames": (x.get("pi") or {}).get("frames")} for x in r.get("recordings", [])[:limit]]
    return {"totals": r.get("totals"), "recordings": recs}, []


def t_camera_image(d: Data, a: dict) -> tuple[Any, list]:
    rec = (a.get("recording_id") or "").strip()
    if not rec:
        # live=1 marks a viewer, which wakes the Pi's camera (it sleeps when nobody watches): wait for a fresh frame
        asked = time.time() * 1000
        s = _dash("/api/state?live=1")
        while s.get("online") and (s.get("frameTs") or 0) < asked - 5000 and time.time() * 1000 - asked < 9000:
            time.sleep(1.5)
            s = _dash("/api/state?live=1")
        if not s.get("frame"):
            return {"error": "no live frame yet (the Pi may be offline or waking up; try again in a few seconds)", "online": s.get("online")}, []
        age = _ago(s.get("frameTs"))
        return {"source": "live camera", "frame_age": age, "online": s.get("online")}, [
            {"src": "data:image/jpeg;base64," + s["frame"], "caption": f"Live camera · {age}"}]
    frames = _dash("/api/frame?rec=" + urllib.parse.quote(rec))
    if not frames:
        return {"error": "that recording has no preview frames"}, []
    at = min(max(float(a.get("at") or 0.5), 0.0), 1.0)
    f = frames[min(len(frames) - 1, int(at * (len(frames) - 1)))]
    jpg = _dash_bytes("/api/frame?id=" + f["id"])
    when = datetime.fromtimestamp(f["ts"] / 1000, timezone.utc).strftime("%b %d %H:%M:%S UTC") if f.get("ts") else ""
    return {"source": f"recording {rec}", "frame": f"{frames.index(f) + 1} of {len(frames)}", "time": when}, [
        {"src": "data:image/jpeg;base64," + base64.b64encode(jpg).decode(), "caption": f"Recording {rec[-6:]} · frame {frames.index(f) + 1}/{len(frames)} · {when}"}]


def _fn(name: str, desc: str, props: dict | None = None, required: list | None = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


NUM, STR, BOOL = {"type": "number"}, {"type": "string"}, {"type": "boolean"}
SERVER_TOOLS: dict[str, tuple[Callable[[Data, dict], tuple[Any, list]], str, dict]] = {
    "city_overview": (t_city_overview, "Reading the citywide model", _fn(
        "city_overview", "Citywide summary: hexagon counts, silent blocks and mean rat risk per borough, and the top rat-risk and top silent-block hexagons.")),
    "search_cells": (t_search_cells, "Searching hexagons", _fn(
        "search_cells", "Find and rank hexagons. Filter by borough, neighbourhood substring, and/or distance from a point; sort by rat_risk (Model B), silence, complaints (Model A), live_detections or nearest.",
        {"borough": STR, "neighborhood": STR, "near_lat": NUM, "near_lon": NUM, "radius_m": NUM,
         "sort_by": {"type": "string", "enum": ["rat_risk", "silence", "complaints", "live_detections", "nearest"]}, "limit": NUM})),
    "get_cell": (t_get_cell, "Looking up a hexagon", _fn(
        "get_cell", "Everything about one hexagon (by h3 id, or the hexagon at lat/lon): scores, the model's top reasons (SHAP), riskiest buildings, best owl mount spots.",
        {"h3": STR, "lat": NUM, "lon": NUM})),
    "geocode": (t_geocode, "Finding the place", _fn(
        "geocode", "NYC address / place / neighbourhood search (NYC GeoSearch). Returns candidates with lat/lon.", {"query": STR}, ["query"])),
    "node_sites": (t_node_sites, "Ranking owl sites", _fn(
        "node_sites", "The model's ranked suggested owl (camera node) sites: where a node adds the most information, with the street-tree mount address.",
        {"borough": STR, "limit": NUM})),
    "model_quality": (t_model_quality, "Checking the backtest", _fn(
        "model_quality", "How good the model is: backtest precision vs 311, AUCs, calibration, owl-spot validation.")),
    "recent_sightings": (t_recent_sightings, "Reading the sightings log", _fn(
        "recent_sightings", "Latest detections posted by owl nodes (rat/person, confidence, hexagon, time). with_images shows the detection crops.",
        {"limit": NUM, "with_images": BOOL})),
    "pi_status": (t_pi_status, "Checking the Pi", _fn(
        "pi_status", "Live status of the team's physical owl node (Raspberry Pi 5): online, motion sensor, IR light, CPU temperature, Wi-Fi, recording.")),
    "pi_activity": (t_pi_activity, "Querying Tiger Data", _fn(
        "pi_activity", "The Pi's motion activity over time from Tiger Data (TimescaleDB): per-minute motion share, detections, motion events, CPU temperature.",
        {"range_minutes": {"type": "number", "enum": [15, 60, 360, 1440, 10080]}})),
    "pi_recordings": (t_pi_recordings, "Listing recordings", _fn(
        "pi_recordings", "The Pi's recordings stored in MongoDB (newest first) with totals.", {"limit": NUM})),
    "camera_image": (t_camera_image, "Getting a camera frame", _fn(
        "camera_image", "A picture from the Pi's camera: the live frame, or a frame from a recording (recording_id from pi_recordings; at = 0..1 position in the clip). The user sees it too.",
        {"recording_id": STR, "at": NUM})),
}
CLIENT_TOOLS: dict[str, tuple[str, dict]] = {
    "get_app_state": ("Reading the map", _fn(
        "get_app_state", "What the user's app shows right now: borough, map mode, camera position, pinned hexagon, and the owls they placed (with sightings).")),
    "screenshot_map": ("Taking a screenshot", _fn(
        "screenshot_map", "Screenshot of the user's current 3D map view. The user sees it in the chat too; you get the image.")),
    # driving the map: each returns once the camera has landed (smooth flights), so screenshot_map right after works
    "fly_to": ("Flying there", _fn(
        "fly_to", "Move the user's map camera to a point (smooth flight). Enters the right borough and pins + flashes the hexagon there. "
        "zoom: street (~300 m), block (default), neighborhood, borough. label: the address or name to show on the pinned card.",
        {"lat": NUM, "lon": NUM, "zoom": {"type": "string", "enum": ["street", "block", "neighborhood", "borough"]}, "label": STR, "h3": STR,
         "borough": STR, "pin": BOOL}, ["lat", "lon"])),
    "set_map_mode": ("Switching the map", _fn(
        "set_map_mode", "Change what the hexagons show: a = what the city sees (311 complaints), b = what's there (rat risk), silence = B minus A (silent blocks).",
        {"mode": {"type": "string", "enum": ["a", "b", "silence"]}}, ["mode"])),
    "enter_borough": ("Changing borough", _fn(
        "enter_borough", "Enter a borough (Manhattan, Brooklyn, Queens, Bronx, Staten Island) with its 3D buildings, or 'citywide' to zoom back out.",
        {"borough": STR}, ["borough"])),
    "show_panel": ("Opening a panel", _fn(
        "show_panel", "Open or close a panel: owls (placed nodes and suggested sites, right), logs (the sightings log with detection crops, left), backtest (the chart, bottom).",
        {"panel": {"type": "string", "enum": ["owls", "logs", "backtest"]}, "open": BOOL}, ["panel"])),
    "select_owl": ("Pulling up the owl", _fn(
        "select_owl", "Select one of the user's placed owls (id from get_app_state) and fly in close to it.", {"owl_id": STR}, ["owl_id"])),
    "show_suggested_site": ("Pulling up the site", _fn(
        "show_suggested_site", "Fly to a suggested owl site by rank (from node_sites) and open its mount-spot options in the Owls panel.",
        {"rank": NUM}, ["rank"])),
    "set_lighting": ("Changing the lighting", _fn(
        "set_lighting", "Day or night lighting for the map (night is the stage look).", {"preset": {"type": "string", "enum": ["day", "night"]}}, ["preset"])),
}
TOOL_SPECS = [t[2] for t in SERVER_TOOLS.values()] + [t[1] for t in CLIENT_TOOLS.values()]


# ---------------------------------------------------------------------------------------------- Grok

def _stream_xai(body: dict, put: Callable[[Any], None]) -> None:
    """Runs in a thread: streams one chat completion, handing each parsed chunk to put(); None at the end."""
    try:
        req = urllib.request.Request(XAI_URL, data=json.dumps(body).encode(), method="POST", headers={
            "Authorization": "Bearer " + os.environ["XAI_API_KEY"], "Content-Type": "application/json", "Accept": "text/event-stream"})
        with urllib.request.urlopen(req, timeout=180) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                put(json.loads(data))
    except urllib.error.HTTPError as e:
        put({"__error__": f"Grok returned {e.code}: {e.read()[:300].decode('utf-8', 'replace')}"})
    except Exception as e:  # noqa: BLE001 - reported to the chat
        put({"__error__": f"Grok request failed: {e}"})
    put(None)


async def _chunks(body: dict):
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    threading.Thread(target=_stream_xai, args=(body, lambda x: loop.call_soon_threadsafe(q.put_nowait, x)), daemon=True).start()
    while (c := await q.get()) is not None:
        yield c


def _image_message(images: list[dict]) -> dict:
    return {"role": "user", "content": [{"type": "text", "text": "(Images from the tool calls above, shown to the user too. Look at them to answer.)"}]
            + [{"type": "image_url", "image_url": {"url": i["src"]}} for i in images]}


def _strip_images(messages: list[dict]) -> list[dict]:
    """The history goes back to the browser without the pictures (they are big and already shown)."""
    out = []
    for m in messages:
        if isinstance(m.get("content"), list):
            text = " ".join(p.get("text", "") for p in m["content"] if p.get("type") == "text")
            n = sum(1 for p in m["content"] if p.get("type") == "image_url")
            m = {**m, "content": f"{text} [{n} image(s) were shown here]".strip()}
        out.append(m)
    return out


def _clean_history(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        raise HTTPException(400, "messages must be a list")
    out = []
    for m in raw[-MAX_HISTORY:]:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant", "tool"):
            continue
        c = m.get("content")
        if c is not None and not isinstance(c, str):
            c = json.dumps(c)
        mm: dict = {"role": m["role"], "content": (c or "")[:MAX_MSG_CHARS]}
        if m["role"] == "assistant" and isinstance(m.get("tool_calls"), list):
            mm["tool_calls"] = [{"id": str(t.get("id")), "type": "function",
                                 "function": {"name": str(t.get("function", {}).get("name")), "arguments": str(t.get("function", {}).get("arguments", "{}"))[:4000]}}
                                for t in m["tool_calls"][:8] if isinstance(t, dict)]
        if m["role"] == "tool":
            mm["tool_call_id"] = str(m.get("tool_call_id"))
        out.append(mm)
    while out and out[0]["role"] == "tool":  # a cut history must not start mid-tool-call
        out.pop(0)
    return out


IMESSAGE_NOTE = """
This user is texting you over iMessage (Photon Spectrum): no map, so the map tools are not available. Plain
sentences and short dash lists, no tables, under ~120 words. Pictures you fetch are sent to them as photos."""


async def run_agent(data: Data, messages: list[dict], emit: Emit, channel: str = "web") -> None:
    imsg = channel == "imessage"
    prompt = system_prompt() + (IMESSAGE_NOTE if imsg else "")
    specs = [t for t in TOOL_SPECS if not (imsg and t["function"]["name"] in CLIENT_TOOLS)]
    for rnd in range(MAX_ROUNDS + 1):
        body = {"model": MODEL, "messages": [{"role": "system", "content": prompt}] + messages,
                "stream": True, "max_tokens": MAX_TOKENS, "temperature": 0.3}
        if REASONING:
            body["reasoning_effort"] = REASONING
        if rnd < MAX_ROUNDS:
            body["tools"] = specs
        text, calls, thinking = "", {}, False
        async for ch in _chunks(body):
            if "__error__" in ch:
                await emit({"type": "error", "text": ch["__error__"]})
                return
            for choice in ch.get("choices", [])[:1]:
                delta = choice.get("delta") or {}
                if delta.get("reasoning_content") and not thinking and not text:
                    thinking = True
                    await emit({"type": "thinking", "state": "start"})
                if thinking and (delta.get("content") or delta.get("tool_calls")):
                    thinking = False
                    await emit({"type": "thinking", "state": "done"})
                if delta.get("content"):
                    text += delta["content"]
                    await emit({"type": "delta", "text": delta["content"]})
                for tc in delta.get("tool_calls") or []:
                    c = calls.setdefault(tc.get("index", len(calls)), {"id": "", "name": "", "args": ""})
                    c["id"] = tc.get("id") or c["id"]
                    f = tc.get("function") or {}
                    if f.get("name"):
                        c["name"] = f["name"]
                    c["args"] += f.get("arguments") or ""
        if thinking:
            await emit({"type": "thinking", "state": "done"})
        ordered = [calls[k] for k in sorted(calls)]
        assistant: dict = {"role": "assistant", "content": text}
        if ordered:
            assistant["tool_calls"] = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["args"] or "{}"}} for c in ordered]
        messages.append(assistant)
        if not ordered:
            break

        images: list[dict] = []
        client: list[dict] = []
        for c in ordered:
            try:
                args = json.loads(c["args"] or "{}")
            except json.JSONDecodeError:
                args = {}
            if c["name"] in CLIENT_TOOLS:
                client.append({"id": c["id"], "name": c["name"], "args": args, "label": CLIENT_TOOLS[c["name"]][0]})
                continue
            fn, label, _ = SERVER_TOOLS.get(c["name"], (None, c["name"], None))
            await emit({"type": "tool", "id": c["id"], "name": c["name"], "label": label, "state": "start"})
            try:
                if fn is None:
                    raise ValueError(f"unknown tool {c['name']}")
                result, imgs = await asyncio.to_thread(fn, data, args)
                ok = not (isinstance(result, dict) and result.get("error"))
            except Exception as e:  # noqa: BLE001 - the model sees the error and can recover
                result, imgs, ok = {"error": str(e)}, [], False
            for i in imgs:
                await emit({"type": "image", **i})
            images += imgs
            await emit({"type": "tool", "id": c["id"], "name": c["name"], "label": label, "state": "done" if ok else "error"})
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result, default=str)[:MAX_MSG_CHARS]})
        if client:
            # the browser runs these and posts again; server images of this round ride along with its results
            await emit({"type": "client_tools", "calls": client, "pending_images": images})
            await emit({"type": "messages", "messages": _strip_images(messages)})
            return
        if images:
            messages.append(_image_message(images))
    await emit({"type": "messages", "messages": _strip_images(messages)})


# ---------------------------------------------------------------------------------------------- route

_hits: dict[str, deque] = defaultdict(deque)


def _rate_ok(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 86_400:
        q.popleft()
    if len(q) >= RATE_PER_DAY or sum(1 for t in q if now - t < 60) >= RATE_PER_MIN:
        return False
    q.append(now)
    return True


def mount_agent(app: FastAPI, store: Store) -> None:
    @app.get("/agent/health")
    async def agent_health():
        return {"ok": bool(os.environ.get("XAI_API_KEY")), "model": MODEL, "node_connected": bool(os.environ.get("AGENT_TOKEN")),
                "tools": [t["function"]["name"] for t in TOOL_SPECS]}

    @app.post("/agent/chat")
    async def agent_chat(request: Request):
        if not os.environ.get("XAI_API_KEY"):
            raise HTTPException(503, "the assistant is not configured (XAI_API_KEY)")
        if not _rate_ok(request.client.host if request.client else "?"):
            raise HTTPException(429, "slow down: too many questions, try again in a minute")
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "request body must be an object")
        month = body.get("month")
        if month is not None and (not isinstance(month, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month)):
            raise HTTPException(400, "month must be YYYY-MM")
        plan_k = body.get("plan_k")
        if plan_k is not None and (type(plan_k) is not int or not 0 <= plan_k <= 10_000):
            raise HTTPException(400, "plan_k must be an integer from 0 to 10000")
        data = Data(store, month, plan_k)
        messages = _clean_history(body.get("messages"))
        # results of browser tools from the previous round
        results = body.get("client_results") or []
        images = [i for i in body.get("pending_images") or [] if isinstance(i, dict) and str(i.get("src", "")).startswith("data:image/")][:4]
        for r in results[:8]:
            if not isinstance(r, dict):
                continue
            messages.append({"role": "tool", "tool_call_id": str(r.get("id")), "content": str(r.get("content", ""))[:MAX_MSG_CHARS]})
            img = r.get("image")
            if isinstance(img, str) and img.startswith("data:image/") and len(img) <= MAX_IMAGE_B64:
                images.append({"src": img, "caption": "map"})
        if images:
            messages.append(_image_message(images))
        if not messages or messages[-1]["role"] not in ("user", "tool"):
            raise HTTPException(400, "nothing to answer")

        q: asyncio.Queue = asyncio.Queue()

        async def emit(ev: dict) -> None:
            await q.put(ev)

        async def work():
            try:
                await run_agent(data, messages, emit, "imessage" if body.get("channel") == "imessage" else "web")
            except Exception as e:  # noqa: BLE001
                await emit({"type": "error", "text": f"assistant error: {e}"})
            await q.put({"type": "done"})

        task = asyncio.create_task(work())

        async def gen():
            try:
                while True:
                    ev = await q.get()
                    yield f"data: {json.dumps(ev, default=str)}\n\n"
                    if ev["type"] == "done":
                        break
            finally:
                task.cancel()

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
