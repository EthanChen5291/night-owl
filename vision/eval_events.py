#!/usr/bin/env python3
"""Event-level metric: run the node's detect logic offline and score *events*, not boxes.

mAP says whether boxes land on the prop; the demo needs something else: when the prop is pushed
across the floor, does the node fire once, and does it stay quiet otherwise. This script runs the
exact code path of ``pi/detect.py`` (Detector -> apply_rules -> EventGate) over

- a held-out positive clip (``--clip`` video or ``--frames`` dir at ``--fps``) with a ``--pushes``
  CSV of ground-truth push times (column ``t_sec``; optional ``label``), and/or
- a negatives-only reel (``--negatives`` video or dir): people, hoodies, bags, shoes, hands, no prop.

Reported: events fired / pushes expected, pushes hit (an event inside ``[t - pre, t + post]``),
false events on the positive clip (outside every window), and on the negatives reel events per
minute. The RUNBOOK gate is 20 demo pushes -> >= 18 hit, and < 0.5 false events / min on the reel.

``--conf 0.4,0.5,0.6`` sweeps the confidence threshold on cached detections (inference runs once at
the lowest value), so tuning CONF for detect.py takes one pass. ``--json out.json`` saves the table.

Example::

    python3 eval_events.py --model pi/rat.onnx --clip clips/rig_pushes_01.mp4 --pushes pushes.csv \\
        --negatives clips/rig_negatives_01.mp4 --conf 0.4,0.5,0.6
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "pi"))

IMG_EXTS = {".jpg", ".jpeg", ".png"}


def read_pushes(path: Path) -> list[float]:
    out = []
    with path.open(newline="") as fh:
        rd = csv.DictReader(fh)
        for row in rd:
            for key in ("t_sec", "t", "ts", "time", "sec"):
                if key in row and row[key].strip():
                    out.append(float(row[key]))
                    break
    return sorted(out)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def iter_source(src: str, fps: float, gray: bool):
    """Yield (t_sec, image) from a video file or a directory of frames."""
    import cv2

    p = Path(src)
    if p.is_dir():
        files = sorted(f for f in p.iterdir() if f.suffix.lower() in IMG_EXTS and not f.name.startswith("_"))
        for i, f in enumerate(files):
            img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE if gray else cv2.IMREAD_COLOR)
            if img is not None:
                yield i / fps, img
        return
    cap = cv2.VideoCapture(str(p))
    if not cap.isOpened():
        raise SystemExit(f"cannot open {src}")
    i = 0
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0 or i / src_fps
        if gray:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        yield t, img
        i += 1
    cap.release()


def run_detector(det, src: str, fps: float, gray: bool, max_side: int):
    """Return list of (t, dets) with dets at the detector's (lowest) conf."""
    import cv2

    rows = []
    n = 0
    t0 = time.monotonic()
    for t, img in iter_source(src, fps, gray):
        h, w = img.shape[:2]
        if max_side and max(h, w) > max_side:  # match the node's 640x480 input
            s = max_side / max(h, w)
            img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        rows.append((t, det.infer(img)))
        n += 1
    dt = time.monotonic() - t0
    print(f"  {src}: {n} frames, {dt:.1f}s ({n / dt if dt else 0:.1f} fps), duration {rows[-1][0] if rows else 0:.1f}s")
    return rows


def replay(rows, conf: float, floor_y: float, hits: int, window: float, cooldown: float,
           min_width: float = None, max_width: float = None):
    from detect import EventGate, apply_rules
    import detect as D

    gate = EventGate(hits, window, cooldown)
    events = []
    for t, dets in rows:
        rats, _ = apply_rules([d for d in dets if d.conf >= conf], floor_y,
                              min_width=D.MIN_RAT_WIDTH if min_width is None else min_width,
                              max_width=D.MAX_RAT_WIDTH if max_width is None else max_width)
        fired = gate.update(t, rats[0] if rats else None)
        if fired:
            events.append((t, fired[0].conf))
    return events


def score_pushes(events, pushes, pre: float, post: float):
    """Maximum one-to-one matching; every extra event counts as a false event."""
    matched_event = {}

    def match(push_index, seen):
        tp = pushes[push_index]
        for event_index, (te, _) in enumerate(events):
            if event_index in seen or not tp - pre <= te <= tp + post:
                continue
            seen.add(event_index)
            if event_index not in matched_event or match(matched_event[event_index], seen):
                matched_event[event_index] = push_index
                return True
        return False

    hit = sum(bool(match(i, set())) for i in range(len(pushes)))
    false = [e for i, e in enumerate(events) if i not in matched_event]
    return hit, false


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="pi/rat.onnx")
    ap.add_argument("--clip", help="positive clip (video) with pushes")
    ap.add_argument("--frames", help="positive clip as a frame directory (with --fps)")
    ap.add_argument("--pushes", help="CSV of push times, column t_sec")
    ap.add_argument("--negatives", help="negatives-only reel: video or frame directory")
    ap.add_argument("--fps", type=float, default=15.0, help="fps to assume for frame directories")
    ap.add_argument("--conf", default=None, help="one value or a comma list to sweep (default: detect.py CONF)")
    ap.add_argument("--floor-y", type=float, default=None)
    ap.add_argument("--min-rat-width", type=float, default=None)
    ap.add_argument("--max-rat-width", type=float, default=None)
    ap.add_argument("--hits", type=int, default=None)
    ap.add_argument("--window", type=float, default=None)
    ap.add_argument("--cooldown", type=float, default=None)
    ap.add_argument("--pre", type=float, default=0.5, help="seconds before a push that still count")
    ap.add_argument("--post", type=float, default=3.0, help="seconds after a push that still count")
    ap.add_argument("--max-side", type=int, default=640, help="downscale input to the node's resolution (0 = off)")
    ap.add_argument("--color", dest="gray", action="store_false", default=None, help="feed colour (World fallback)")
    ap.add_argument("--names", help="comma-separated class names if not one of the two known models")
    ap.add_argument("--json", metavar="PATH", help="write results as JSON")
    ap.add_argument("--min-pushes", type=int, default=20, help="minimum annotated pushes for the demo gate")
    ap.add_argument("--min-neg-minutes", type=float, default=3.0, help="minimum negatives duration for the demo gate")
    args = ap.parse_args(argv)

    if not (args.clip or args.frames or args.negatives):
        ap.error("give --clip/--frames (with --pushes) and/or --negatives")
    if (args.clip or args.frames) and not args.pushes:
        ap.error("positive footage requires --pushes; unannotated events cannot pass the gate")
    try:
        import detect as D
    except ImportError as e:
        print(f"cannot import pi/detect.py: {e}", file=sys.stderr)
        return 2
    try:
        import cv2  # noqa: F401
        import onnxruntime  # noqa: F401
    except ImportError as e:
        print(f"missing dependency: {e}", file=sys.stderr)
        return 2

    gray = D.GRAY if args.gray is None else args.gray
    confs = [float(c) for c in (args.conf or str(D.CONF)).split(",")]
    floor_y = D.FLOOR_Y if args.floor_y is None else args.floor_y
    hits = D.HITS_NEEDED if args.hits is None else args.hits
    window = D.HIT_WINDOW_S if args.window is None else args.window
    cooldown = D.EVENT_COOLDOWN_S if args.cooldown is None else args.cooldown
    min_width = D.MIN_RAT_WIDTH if args.min_rat_width is None else args.min_rat_width
    max_width = D.MAX_RAT_WIDTH if args.max_rat_width is None else args.max_rat_width
    names = [s.strip() for s in args.names.split(",")] if args.names else None

    det = D.Detector(args.model, D.IMGSZ, gray, min(confs), D.IOU, names=names)
    print(f"model {args.model} gray={gray} floor_y {floor_y} hits {hits}/{window}s cooldown {cooldown}s")

    pos_rows = neg_rows = None
    pushes = []
    if args.clip or args.frames:
        pos_rows = run_detector(det, args.clip or args.frames, args.fps, gray, args.max_side)
        if args.pushes:
            pushes = read_pushes(Path(args.pushes))
        else:
            print("  (no --pushes: every event on the positive clip is reported, none scored)")
    if args.negatives:
        neg_rows = run_detector(det, args.negatives, args.fps, gray, args.max_side)

    results = []
    print()
    print(f"{'conf':>5} {'events':>7} {'pushes':>7} {'hit':>5} {'recall':>7} {'false':>6} | {'neg ev':>6} {'neg/min':>8}")
    for c in confs:
        r = {"conf": c}
        if pos_rows is not None:
            ev = replay(pos_rows, c, floor_y, hits, window, cooldown, min_width, max_width)
            hit, false = score_pushes(ev, pushes, args.pre, args.post) if pushes else (0, ev)
            r.update(events=len(ev), pushes=len(pushes), hit=hit,
                     recall=(hit / len(pushes)) if pushes else None, false_events=len(false),
                     event_times=[round(t, 2) for t, _ in ev])
        if neg_rows is not None:
            nev = replay(neg_rows, c, floor_y, hits, window, cooldown, min_width, max_width)
            dur = (neg_rows[-1][0] - neg_rows[0][0] + 1 / args.fps) if neg_rows else 0
            r.update(neg_events=len(nev), neg_per_min=60.0 * len(nev) / dur if dur > 0 else None,
                     neg_minutes=dur / 60, neg_event_times=[round(t, 2) for t, _ in nev])
        results.append(r)
        recall_s = f"{r['recall']:.0%}" if r.get("recall") is not None else "-"
        npm_s = f"{r['neg_per_min']:.2f}" if r.get("neg_per_min") is not None else "-"
        print(f"{c:>5.2f} {r.get('events', '-'):>7} {r.get('pushes', '-'):>7} {r.get('hit', '-'):>5} "
              f"{recall_s:>7} {r.get('false_events', '-'):>6} | {r.get('neg_events', '-'):>6} {npm_s:>8}")

    eligible = [r for r in results if len(pushes) >= args.min_pushes and
                r.get("neg_minutes", 0) >= args.min_neg_minutes and r.get("neg_per_min") is not None]
    passing = [r for r in eligible if r["recall"] >= 0.9 and r["neg_per_min"] < 0.5]
    best = min(passing, key=lambda r: (-r["recall"], r["false_events"], r["neg_per_min"], r["conf"])) if passing else None
    status = "PASS" if best else "FAIL" if eligible else "NOT_EVALUATED"
    print(f"\nGATE {status}" + (f" at conf {best['conf']}" if best else
          f" (need {args.min_pushes} annotated pushes and {args.min_neg_minutes:g} min negatives)" if not eligible else ""))
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"model": str(Path(args.model).resolve()),
                                   "model_sha256": sha256(Path(args.model)),
                                   "gray": gray, "floor_y": floor_y,
                                   "min_rat_width": min_width, "max_rat_width": max_width,
                                   "hits": hits, "window": window, "cooldown": cooldown,
                                   "gate_status": status, "selected_conf": best["conf"] if best else None,
                                   "results": results}, indent=2) + "\n")
        print(f"wrote {args.json}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
