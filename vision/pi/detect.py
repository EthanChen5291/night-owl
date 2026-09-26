#!/usr/bin/env python3
"""Node detector: camera -> ONNX YOLO -> rules -> event -> POST /event -> LED. Runs on the Pi CPU.

Only numpy, opencv-python-headless and onnxruntime are needed (the offline wheels in ``wheels/``);
``gpiozero`` is optional and only used for the LED. Nothing here imports ultralytics.

Pipeline per frame (README §4)::

    letterbox to IMGSZ -> ONNX (handles [1,6,N] and [1,N,6] outputs) -> NMS
      -> floor rule: keep rat boxes whose centre y > FLOOR_Y (camera looks down; the top of the
         frame is the far wall / people's legs)
      -> person suppression: drop rat boxes overlapping a person box (IoU > PERSON_IOU, or more
         than PERSON_CONTAIN of the rat box inside the person box: IoU alone misses a small box
         inside a big one)
      -> hit counter: HITS_NEEDED hits inside HIT_WINDOW_S seconds -> one event
      -> cooldown: at most one event per EVENT_COOLDOWN_S
      -> POST {API_URL}/event (urllib, 2 s timeout, failures are logged and ignored)
      -> LED blink on LED_PIN

The event body is exactly the contract::

    {"node_id": NODE_ID, "h3": DEMO_H3, "ts": "<ISO 8601>", "class": "rat", "conf": 0.87,
     "n_hits": 3, "bbox": [x, y, w, h],           # normalised 0-1, top-left + size
     "crop_b64": "<base64 JPEG of the rat crop>",  # crop only, never the full frame
     "fw": "0.1.0"}

The full frame stays in RAM. ``--save-events DIR`` also writes the JSON and the crop locally for
the deck and for debugging without a server.

Models: ``rat.onnx`` (ours, classes rat/person, produced by ``train.sh``) is the default;
``--model world_rat_person.onnx`` is the zero-training YOLO-World fallback whose classes are
``stuffed animal`` / ``person``; both are mapped to ``rat`` / ``person`` here. Set ``GRAY`` to
match ``make_dataset.py`` for the model in use (the World model was not trained gray; pass
``--color`` for it).

Examples::

    python3 detect.py --mock ../frames --show --no-post          # Mac
    python3 detect.py --model world_rat_person.onnx --color      # Pi, hour-6 gate
    BARN_OWL_API=http://192.168.7.1:8000 python3 detect.py --save-events events
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

# ---- constants (README §4) ----
MODEL = "rat.onnx"
FALLBACK_MODEL = "world_rat_person.onnx"
IMGSZ = 416
GRAY = True
CONF = 0.5
IOU = 0.45
FLOOR_Y = 0.40
PERSON_IOU = 0.3        # drop a rat box whose IoU with a person box exceeds this ...
PERSON_CONTAIN = 0.7    # ... or whose own area is mostly inside a person box (feet standing over it)
HITS_NEEDED = 3
HIT_WINDOW_S = 1.0
EVENT_COOLDOWN_S = 2.0
NODE_ID = "demo-01"
DEMO_H3 = "892a100d2c3ffff"
API_URL = os.environ.get("BARN_OWL_API", "http://192.168.7.1:8000")
LED_PIN = 17
FW = "0.1.0"
CROP_MAX_SIDE = 160
CROP_JPEG_QUALITY = 80

# class names per model file, and how they map onto the contract's class names
MODEL_NAMES = {
    "rat.onnx": ["rat", "person"],
    "world_rat_person.onnx": ["stuffed animal", "person"],
}
CLASS_MAP = {"rat": "rat", "stuffed animal": "rat", "person": "person"}


# ---------------------------------------------------------------- geometry
def iou_xywh(a, b) -> float:
    ax0, ay0, ax1, ay1 = a[0], a[1], a[0] + a[2], a[1] + a[3]
    bx0, by0, bx1, by1 = b[0], b[1], b[0] + b[2], b[1] + b[3]
    iw = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    ih = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def nms(boxes_xyxy, scores, iou_thr: float):
    """Greedy NMS on numpy arrays; returns kept indices (descending score)."""
    import numpy as np

    if len(boxes_xyxy) == 0:
        return []
    x0, y0, x1, y1 = boxes_xyxy.T
    areas = (x1 - x0) * (y1 - y0)
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        rest = order[1:]
        iw = np.maximum(0, np.minimum(x1[i], x1[rest]) - np.maximum(x0[i], x0[rest]))
        ih = np.maximum(0, np.minimum(y1[i], y1[rest]) - np.maximum(y0[i], y0[rest]))
        inter = iw * ih
        iou = inter / (areas[i] + areas[rest] - inter + 1e-9)
        order = rest[iou <= iou_thr]
    return keep


class Det:
    """One detection: contract class name, confidence, normalised [x, y, w, h] (top-left + size)."""

    __slots__ = ("cls", "conf", "x", "y", "w", "h")

    def __init__(self, cls: str, conf: float, x: float, y: float, w: float, h: float):
        self.cls, self.conf, self.x, self.y, self.w, self.h = cls, float(conf), float(x), float(y), float(w), float(h)

    @property
    def bbox(self):
        return [round(self.x, 4), round(self.y, 4), round(self.w, 4), round(self.h, 4)]

    @property
    def cy(self):
        return self.y + self.h / 2

    def __repr__(self):
        return f"{self.cls} {self.conf:.2f} {self.bbox}"


# ---------------------------------------------------------------- detector
class Detector:
    def __init__(self, model: str = MODEL, imgsz: int = IMGSZ, gray: bool = GRAY, conf: float = CONF,
                 iou: float = IOU, names=None, threads: int | None = None, layout: str = "auto"):
        import onnxruntime as ort

        self.path = str(model)
        self.imgsz, self.gray, self.conf, self.iou, self.layout = imgsz, gray, conf, iou, layout
        self.names = list(names) if names else MODEL_NAMES.get(Path(model).name, ["rat", "person"])
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads or max(1, min(4, os.cpu_count() or 1))
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(self.path, so, providers=["CPUExecutionProvider"])
        inp = self.sess.get_inputs()[0]
        self.input_name = inp.name
        shp = inp.shape
        if len(shp) == 4 and isinstance(shp[2], int) and isinstance(shp[3], int):
            self.imgsz = shp[2]  # trust the graph over the constant
        self.in_channels = shp[1] if len(shp) == 4 and isinstance(shp[1], int) else 3

    # -- pre
    def letterbox(self, img):
        import cv2
        import numpy as np

        h, w = img.shape[:2]
        r = min(self.imgsz / h, self.imgsz / w)
        nw, nh = max(1, int(round(w * r))), max(1, int(round(h * r)))
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR if r > 1 else cv2.INTER_AREA)
        dx, dy = (self.imgsz - nw) // 2, (self.imgsz - nh) // 2
        if resized.ndim == 2:
            canvas = np.full((self.imgsz, self.imgsz), 114, dtype=np.uint8)
            canvas[dy:dy + nh, dx:dx + nw] = resized
        else:
            canvas = np.full((self.imgsz, self.imgsz, resized.shape[2]), 114, dtype=np.uint8)
            canvas[dy:dy + nh, dx:dx + nw] = resized
        return canvas, r, dx, dy

    def preprocess(self, img):
        """img: HxW gray or HxWx3 BGR (uint8). Returns NCHW float32 in [0,1]."""
        import cv2
        import numpy as np

        if self.gray:
            g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            lb, r, dx, dy = self.letterbox(g)
            chw = np.repeat(lb[None], 3, axis=0) if self.in_channels == 3 else lb[None]
        else:
            b = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            lb, r, dx, dy = self.letterbox(b)
            chw = lb[:, :, ::-1].transpose(2, 0, 1)  # BGR -> RGB, HWC -> CHW
        x = np.ascontiguousarray(chw, dtype=np.float32)[None] / 255.0
        return x, r, dx, dy

    # -- post
    def _looks_end2end(self, out) -> bool:
        import numpy as np

        if out.shape[1] != 6:
            return False
        cls = out[:, 5]
        return bool(np.all(cls == np.floor(cls)) and cls.max() <= len(self.names) - 1
                    and np.all(out[:, 2] >= out[:, 0]) and np.all(out[:, 3] >= out[:, 1])
                    and out[:, 4].max() <= 1.0)

    def decode(self, out, r, dx, dy, orig_w, orig_h):
        """Accepts [1,4+nc,N], [1,N,4+nc] (raw) or [1,N,6] (x1,y1,x2,y2,conf,cls after in-graph NMS)."""
        import numpy as np

        nc = len(self.names)
        if out.ndim == 3:
            out = out[0]
        layout = self.layout
        if layout == "auto":
            if out.shape[0] == 4 + nc and out.shape[1] != 4 + nc:
                layout = "raw_cn"
            elif out.shape[1] == 4 + nc and out.shape[0] != 4 + nc:
                layout = "end2end" if self._looks_end2end(out) else "raw_nc"
            elif out.shape[1] == 6 and self._looks_end2end(out):
                layout = "end2end"
            else:
                layout = "raw_cn" if out.shape[0] < out.shape[1] else "raw_nc"
        if layout == "raw_cn":
            out = out.T
        if layout == "end2end":
            m = out[:, 4] >= self.conf
            xyxy, conf, cls = out[m, :4], out[m, 4], out[m, 5].astype(int)
        else:
            scores = out[:, 4:4 + nc]
            cls = scores.argmax(1)
            conf = scores[np.arange(len(scores)), cls]
            m = conf >= self.conf
            xywh, conf, cls = out[m, :4], conf[m], cls[m]
            xyxy = np.empty_like(xywh)
            xyxy[:, 0] = xywh[:, 0] - xywh[:, 2] / 2
            xyxy[:, 1] = xywh[:, 1] - xywh[:, 3] / 2
            xyxy[:, 2] = xywh[:, 0] + xywh[:, 2] / 2
            xyxy[:, 3] = xywh[:, 1] + xywh[:, 3] / 2
            keep = []
            for c in np.unique(cls):
                idx = np.where(cls == c)[0]
                keep.extend(idx[k] for k in nms(xyxy[idx], conf[idx], self.iou))
            xyxy, conf, cls = xyxy[keep], conf[keep], cls[keep]
        dets = []
        for (x0, y0, x1, y1), p, c in zip(xyxy, conf, cls):
            # undo letterbox, normalise, clip
            x0, x1 = (x0 - dx) / r, (x1 - dx) / r
            y0, y1 = (y0 - dy) / r, (y1 - dy) / r
            x0, x1 = max(0.0, min(orig_w, x0)), max(0.0, min(orig_w, x1))
            y0, y1 = max(0.0, min(orig_h, y0)), max(0.0, min(orig_h, y1))
            if x1 - x0 < 1 or y1 - y0 < 1:
                continue
            name = self.names[int(c)] if int(c) < len(self.names) else str(int(c))
            dets.append(Det(CLASS_MAP.get(name, name), p, x0 / orig_w, y0 / orig_h, (x1 - x0) / orig_w, (y1 - y0) / orig_h))
        dets.sort(key=lambda d: -d.conf)
        return dets

    def infer(self, img) -> list:
        h, w = img.shape[:2]
        x, r, dx, dy = self.preprocess(img)
        out = self.sess.run(None, {self.input_name: x})[0]
        return self.decode(out, r, dx, dy, w, h)


# ---------------------------------------------------------------- rules
def contained_frac(a, b) -> float:
    """Fraction of box a's area that lies inside box b (both [x, y, w, h])."""
    iw = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return (iw * ih) / (a[2] * a[3]) if a[2] * a[3] > 0 else 0.0


def apply_rules(dets: list, floor_y: float = FLOOR_Y, person_iou: float = PERSON_IOU, person_contain: float = PERSON_CONTAIN):
    """Floor rule + person suppression. Returns (rats_kept, persons)."""
    persons = [d for d in dets if d.cls == "person"]
    rats = [d for d in dets if d.cls == "rat" and d.cy > floor_y]
    if persons:
        def clear(r):
            rb = [r.x, r.y, r.w, r.h]
            for p in persons:
                pb = [p.x, p.y, p.w, p.h]
                if iou_xywh(rb, pb) > person_iou or contained_frac(rb, pb) > person_contain:
                    return False
            return True
        rats = [r for r in rats if clear(r)]
    return rats, persons


class EventGate:
    """HITS_NEEDED hits within HIT_WINDOW_S -> event; then nothing for EVENT_COOLDOWN_S."""

    def __init__(self, hits_needed: int = HITS_NEEDED, window_s: float = HIT_WINDOW_S, cooldown_s: float = EVENT_COOLDOWN_S):
        self.hits_needed, self.window_s, self.cooldown_s = hits_needed, window_s, cooldown_s
        self.hits = deque()  # (ts, det)
        self.last_event_ts = -1e9
        self.n_events = 0

    def update(self, ts: float, best):
        """best: the best rat Det this frame or None. Returns (det, n_hits) when an event fires."""
        while self.hits and ts - self.hits[0][0] > self.window_s:
            self.hits.popleft()
        if best is None:
            return None
        self.hits.append((ts, best))
        if len(self.hits) < self.hits_needed or ts - self.last_event_ts < self.cooldown_s:
            return None
        n = len(self.hits)
        top = max((d for _, d in self.hits), key=lambda d: d.conf)
        self.hits.clear()
        self.last_event_ts = ts
        self.n_events += 1
        return top, n


# ---------------------------------------------------------------- event output
def crop_b64(frame, det: Det, max_side: int = CROP_MAX_SIDE, quality: int = CROP_JPEG_QUALITY) -> str:
    import cv2

    h, w = frame.shape[:2]
    x0, y0 = int(det.x * w), int(det.y * h)
    x1, y1 = int((det.x + det.w) * w), int((det.y + det.h) * h)
    crop = frame[max(0, y0):max(y0 + 1, y1), max(0, x0):max(x0 + 1, x1)]
    ch, cw = crop.shape[:2]
    if max(ch, cw) > max_side:
        s = max_side / max(ch, cw)
        crop = cv2.resize(crop, (max(1, int(cw * s)), max(1, int(ch * s))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf.tobytes()).decode("ascii") if ok else ""


def make_event(det: Det, n_hits: int, frame, node_id: str = NODE_ID, h3: str = DEMO_H3, ts: float | None = None) -> dict:
    when = datetime.fromtimestamp(ts if ts is not None else time.time(), tz=timezone.utc)
    return {
        "node_id": node_id,
        "h3": h3,
        "ts": when.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "class": "rat",
        "conf": round(det.conf, 3),
        "n_hits": int(n_hits),
        "bbox": det.bbox,
        "crop_b64": crop_b64(frame, det),
        "fw": FW,
    }


def post_event(api_url: str, body: dict, timeout: float = 2.0) -> tuple[bool, str]:
    import urllib.error
    import urllib.request

    data = json.dumps(body).encode()
    req = urllib.request.Request(api_url.rstrip("/") + "/event", data=data, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": f"barn-owl-node/{FW}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"{resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 - network is best effort on stage
        return False, type(e).__name__


class Led:
    def __init__(self, pin: int = LED_PIN):
        self.led = None
        try:
            from gpiozero import LED

            self.led = LED(pin)
        except Exception:  # noqa: BLE001 - no gpiozero / not a Pi
            self.led = None

    def blink(self, n: int = 3):
        if self.led is not None:
            try:
                self.led.blink(on_time=0.08, off_time=0.08, n=n, background=True)
            except Exception:  # noqa: BLE001
                pass


def save_event(out_dir: Path, body: dict, index: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"event_{index:04d}_{body['ts'].replace(':', '').replace('.', '')}"
    (out_dir / f"{stem}.json").write_text(json.dumps(body, indent=1))
    if body.get("crop_b64"):
        (out_dir / f"{stem}.jpg").write_bytes(base64.b64decode(body["crop_b64"]))


# ---------------------------------------------------------------- main loop
def draw(frame_bgr, rats, persons, dropped, gate: EventGate, fps: float):
    import cv2

    h, w = frame_bgr.shape[:2]
    cv2.line(frame_bgr, (0, int(FLOOR_Y * h)), (w, int(FLOOR_Y * h)), (80, 80, 80), 1)
    for d, col in [(d, (0, 200, 0)) for d in rats] + [(d, (255, 120, 0)) for d in persons] + [(d, (0, 0, 200)) for d in dropped]:
        x0, y0 = int(d.x * w), int(d.y * h)
        cv2.rectangle(frame_bgr, (x0, y0), (int((d.x + d.w) * w), int((d.y + d.h) * h)), col, 2)
        cv2.putText(frame_bgr, f"{d.cls} {d.conf:.2f}", (x0, max(12, y0 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)
    cv2.putText(frame_bgr, f"{fps:.1f} fps  hits {len(gate.hits)}/{gate.hits_needed}  events {gate.n_events}",
                (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return frame_bgr


def main(argv=None) -> int:
    from camera import add_camera_args, frames_from_args  # local module, no heavy imports

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_camera_args(ap)
    ap.add_argument("--model", default=MODEL, help=f"ONNX file (default {MODEL}; fallback {FALLBACK_MODEL})")
    ap.add_argument("--names", help="comma-separated class names if the model is neither of the known two")
    ap.add_argument("--conf", type=float, default=CONF)
    ap.add_argument("--iou", type=float, default=IOU)
    ap.add_argument("--floor-y", type=float, default=FLOOR_Y)
    ap.add_argument("--person-iou", type=float, default=PERSON_IOU)
    ap.add_argument("--person-contain", type=float, default=PERSON_CONTAIN)
    ap.add_argument("--hits", type=int, default=HITS_NEEDED)
    ap.add_argument("--window", type=float, default=HIT_WINDOW_S, help="seconds in which --hits must occur")
    ap.add_argument("--cooldown", type=float, default=EVENT_COOLDOWN_S)
    ap.add_argument("--gray", dest="gray", action="store_true", default=GRAY)
    ap.add_argument("--color", dest="gray", action="store_false", help="feed colour (use with the World fallback)")
    ap.add_argument("--api", default=API_URL, help="server base URL (env BARN_OWL_API)")
    ap.add_argument("--node-id", default=NODE_ID)
    ap.add_argument("--h3", default=DEMO_H3)
    ap.add_argument("--no-post", action="store_true", help="never POST (Mac testing)")
    ap.add_argument("--save-events", metavar="DIR", help="write event JSON + crop here")
    ap.add_argument("--show", action="store_true", help="cv2.imshow with boxes (Mac / desktop)")
    ap.add_argument("--max-frames", type=int, default=0, help="stop after N frames (0 = run until ^C / mock ends)")
    ap.add_argument("--threads", type=int, default=None, help="onnxruntime intra-op threads (default: min(4, cores))")
    ap.add_argument("--layout", choices=["auto", "raw_cn", "raw_nc", "end2end"], default="auto", help="ONNX output layout")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    model = Path(args.model)
    if not model.is_file():
        here = Path(__file__).resolve().parent / model.name
        if here.is_file():
            model = here
        elif Path(FALLBACK_MODEL).is_file() or (Path(__file__).resolve().parent / FALLBACK_MODEL).is_file():
            print(f"{args.model} not found, using fallback {FALLBACK_MODEL}", file=sys.stderr)
            model = Path(FALLBACK_MODEL) if Path(FALLBACK_MODEL).is_file() else Path(__file__).resolve().parent / FALLBACK_MODEL
        else:
            print(f"no model: {args.model} (train.sh makes pi/rat.onnx; the World fallback is {FALLBACK_MODEL})", file=sys.stderr)
            return 2
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
    except ImportError as e:
        print(f"missing dependency: {e}. On the Pi: pip install --no-index --find-links wheels/ onnxruntime numpy opencv-python-headless",
              file=sys.stderr)
        return 2

    names = [s.strip() for s in args.names.split(",")] if args.names else None
    det = Detector(str(model), IMGSZ, args.gray, args.conf, args.iou, names=names, threads=args.threads, layout=args.layout)
    gate = EventGate(args.hits, args.window, args.cooldown)
    led = Led()
    save_dir = Path(args.save_events) if args.save_events else None
    print(f"model {model.name} classes {det.names} imgsz {det.imgsz} gray={args.gray} conf {args.conf} "
          f"floor_y {args.floor_y} hits {args.hits}/{args.window}s cooldown {args.cooldown}s "
          f"api {'(off)' if args.no_post else args.api} node {args.node_id} h3 {args.h3}", flush=True)

    n = 0
    t_start = time.monotonic()
    t_last_print = t_start
    fps = 0.0
    try:
        for fr in frames_from_args(args, pace=args.mock is not None and args.show):
            n += 1
            img = fr.gray if args.gray else fr.bgr
            t0 = time.monotonic()
            dets = det.infer(img)
            rats, persons = apply_rules(dets, args.floor_y, args.person_iou, args.person_contain)
            dropped = [d for d in dets if d.cls == "rat" and d not in rats]
            best = rats[0] if rats else None
            fired = gate.update(fr.ts, best)
            dt = time.monotonic() - t0
            fps = 0.9 * fps + 0.1 / max(dt, 1e-6) if fps else 1 / max(dt, 1e-6)

            if fired:
                top, n_hits = fired
                body = make_event(top, n_hits, fr.bgr if fr.has_color else fr.gray, args.node_id, args.h3, fr.ts)
                status = "no-post"
                if not args.no_post:
                    ok, status = post_event(args.api, body)
                    status = ("POST ok " if ok else "POST FAIL ") + status
                if save_dir:
                    save_event(save_dir, body, gate.n_events)
                led.blink()
                print(f"EVENT #{gate.n_events} ts={body['ts']} conf={body['conf']} n_hits={n_hits} bbox={body['bbox']} "
                      f"crop={len(body['crop_b64'])}B {status}", flush=True)

            if args.show:
                import cv2
                view = draw(fr.bgr.copy() if fr.has_color else cv2.cvtColor(fr.gray, cv2.COLOR_GRAY2BGR), rats, persons, dropped, gate, fps)
                cv2.imshow("detect", view)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            elif not args.quiet and time.monotonic() - t_last_print > 5:
                t_last_print = time.monotonic()
                print(f"frame {n} infer {dt * 1000:.0f} ms ({fps:.1f} fps) rats {len(rats)} persons {len(persons)} "
                      f"hits {len(gate.hits)} events {gate.n_events}", flush=True)
            if args.max_frames and n >= args.max_frames:
                break
    except KeyboardInterrupt:
        pass
    elapsed = time.monotonic() - t_start
    print(f"done: {n} frames in {elapsed:.1f}s ({n / elapsed if elapsed else 0:.1f} fps incl. camera), events {gate.n_events}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
