"""Render short NightOwl training clips from saved, real run artifacts.

Run with vision/.venv/bin/python. Requires ffmpeg on PATH. The video uses only
Saved training history and the fixed zoom15_b validation clip, which was reused
for model selection. It never reads independent test recordings. V1 and V2
retain the historical V3 captions; V3 uses the locked V4 candidate and report.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
CLIP = ROOT / "vision/clips/zoom15_b.mp4"
OUT_DIR = ROOT / "pitch/out"
W, H, FPS = 1280, 720, 15
NAVY = (16, 38, 53)
INK = (232, 248, 240)
MINT = (174, 229, 210)
TEAL = (31, 192, 188)
CORAL = (217, 108, 80)
MUTED = (155, 180, 178)
GRID = (43, 75, 82)

FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)


def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (W, H), NAVY)
    return im, ImageDraw.Draw(im)


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int,
          color=MINT, bold=False) -> None:
    draw.text(xy, value, font=font(size, bold), fill=color)


def input_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def intro_frame(i: int, count: int, version: str) -> Image.Image:
    im, d = canvas()
    label(d, (80, 110), "BARN OWL", 86, INK, True)
    label(d, (84, 230), "Plush detector training", 52, MINT)
    d.rectangle((84, 340, 1180, 344), fill=TEAL)
    label(d, (84, 405), "Real training log. Recorded camera footage.", 34, INK)
    candidate = "V4" if version == "v3" else "V3"
    label(d, (84, 615), f"Room-lit toy rat  |  {candidate} candidate  |  26 Sep 2026  |  {version.upper()}", 23, MUTED)
    return im


def chart_frame(i: int, count: int, rows: list[dict], version: str) -> Image.Image:
    im, d = canvas()
    label(d, (80, 46), "150 epochs from the saved training log", 48, INK, True)
    label(d, (82, 111), "Trainer validation mAP50, both classes", 27, MINT)
    label(d, (940, 115), f"epoch {max(1, round((i + 1) * len(rows) / count)):03d}/150", 25, INK, True)

    left, right, top, bottom = 110, 1180, 200, 545
    for yv in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = bottom - yv * (bottom - top)
        d.line((left, y, right, y), fill=GRID, width=2)
        label(d, (61, round(y - 14)), f"{yv:.2f}", 19, MUTED)
    for ep in (1, 30, 60, 90, 120, 150):
        x = left + (ep - 1) / 149 * (right - left)
        d.line((x, bottom, x, bottom + 9), fill=MUTED, width=2)
        label(d, (round(x - 15), bottom + 17), str(ep), 18, MUTED)

    metrics = [float(r["metrics/mAP50(B)"]) for r in rows]
    n = max(1, round((i + 1) * len(rows) / count))
    pts = [(left + j / 149 * (right - left), bottom - metrics[j] * (bottom - top)) for j in range(n)]
    if len(pts) > 1:
        d.line(pts, fill=TEAL, width=6, joint="curve")
    x, y = pts[-1]
    d.ellipse((x-8, y-8, x+8, y+8), fill=MINT)
    candidate = "V4" if version == "v3" else "V3"
    label(d, (85, 625), f"Source: results.csv from the completed {candidate} training run", 24, MUTED)
    label(d, (85, 660), "Fixed validation clips were reused while tuning", 22, MUTED)
    return im


def fitted_crop(frame: np.ndarray, box: list[float]) -> Image.Image:
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    pad = 15
    x1, y1 = max(0, x1-pad), max(0, y1-pad)
    x2, y2 = min(frame.shape[1], x2+pad), min(frame.shape[0], y2+pad)
    roi = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2RGB)
    result = Image.fromarray(roi)
    result.thumbnail((310, 310), Image.Resampling.LANCZOS)
    return result


def footage_frame(frame: np.ndarray, box: list[float] | None,
                  conf: float | None, version: str) -> Image.Image:
    im, d = canvas()
    label(d, (80, 40), "ONNX inference on recorded camera footage", 43, INK, True)
    subtitle = "Metal-table validation clip used during tuning" if version == "v3" else "Held-out metal-table clip used during tuning"
    label(d, (82, 96), f"{subtitle}  |  room light", 23, MINT)

    raw = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).resize((720, 540), Image.Resampling.BILINEAR)
    im.paste(raw, (80, 145))
    d = ImageDraw.Draw(im)
    d.rectangle((80, 145, 800, 685), outline=GRID, width=2)
    if box is not None:
        sx, sy = 720/640, 540/480
        x1,y1,x2,y2 = box
        d.rectangle((80+x1*sx,145+y1*sy,80+x2*sx,145+y2*sy),outline=TEAL,width=5)
        crop = fitted_crop(frame, box)
        im.paste(crop, (886 + (310-crop.width)//2, 190 + (310-crop.height)//2))
        d = ImageDraw.Draw(im)
        d.rectangle((884,188,1198,502),outline=TEAL,width=3)
        label(d,(887,530), f"plush  {conf:.2f}",31,MINT,True)
    else:
        label(d,(895,310),"No rat box",30,MUTED)
    label(d,(885,607),"Actual model output",25,INK)
    label(d,(885,640),"Recorded video, not live Pi",21,MUTED)
    return im


def closing_frame(i: int, count: int, version: str) -> Image.Image:
    im, d = canvas()
    if version == "v3":
        label(d, (80, 56), "V4 rat AP50: tuned vs reserved", 49, INK, True)
        label(d, (82, 126), "Locked ONNX  |  square-416 box evaluation", 26, MINT)
        label(d, (80, 225), ".958", 90, TEAL, True)
        label(d, (81, 337), "Tuned validation  |  49 frames", 28, INK)
        label(d, (651, 225), ".926", 90, TEAL, True)
        label(d, (651, 337), "Reserved clips  |  59 frames", 28, INK)
        d.rectangle((80, 475, 1190, 479), fill=GRID)
        label(d, (81, 520), "Same camera, table, and capture session", 36, CORAL, True)
        label(d, (81, 619), "New-room and live Pi tests pending  |  AP50 is not accuracy", 24, MUTED)
        return im
    if version == "v2":
        label(d, (80, 56), "Rat AP50: tuned vs independent", 49, INK, True)
        label(d, (82, 126), "V3 candidate  |  fixed validation clips reused during tuning", 26, MINT)
        label(d, (80, 225), ".943", 90, TEAL, True)
        label(d, (81, 337), "Tuned validation", 31, INK)
        label(d, (651, 225), ".870", 90, CORAL, True)
        label(d, (651, 337), "Independent test", 31, INK)
        d.rectangle((80, 475, 1190, 479), fill=GRID)
        label(d, (81, 520), "Fresh new-angle clip: .844  |  .90 target not met", 34, CORAL, True)
        label(d, (81, 619), "Room-lit plush only  |  physical Pi and formal event gate pending", 24, MUTED)
        return im
    label(d, (80, 56), "Tuned validation  |  rat AP50", 50, INK, True)
    label(d, (82, 126), "Fixed clips reused to choose the model", 27, MINT)
    metrics = [(".943", "combined"), (".995", "metal table"), (".817", "floor")]
    for col, (value, name) in enumerate(metrics):
        x = 80 + col * 400
        label(d, (x, 240), value, 82, TEAL, True)
        label(d, (x, 344), name, 31, INK)
    d.rectangle((80, 490, 1190, 494), fill=GRID)
    label(d, (81, 540), "Independent scene test pending", 39, CORAL, True)
    label(d, (81, 619), "Room-lit plush only  |  physical Pi and formal event gate pending", 24, MUTED)
    return im


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", choices=["v1", "v2", "v3"], default="v3")
    args = parser.parse_args()
    run_name = "modal-rat-v4-20260926" if args.version == "v3" else "modal-rat-v3-expanded-20260926"
    run = ROOT / "vision/runs" / run_name
    csv_path = run / "results.csv"
    model_path = run / "rat.onnx"
    out = OUT_DIR / f"nightowl-training-demo-{args.version}.mp4"
    preview_dir = ROOT / f"pitch/.build/training-video-preview-{args.version}"
    rows = list(csv.DictReader(csv_path.open(newline="")))
    assert len(rows) == 150
    out.parent.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(str(model_path), task="detect")
    cap = cv2.VideoCapture(str(CLIP))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot read {CLIP}")

    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
               "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
               "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "22",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert proc.stdin is not None

    counts = {"intro":24,"chart":90,"footage":68,"close":52}
    total = sum(counts.values())
    written = 0

    def emit(im: Image.Image, preview_name: str | None = None) -> None:
        nonlocal written
        if preview_name:
            im.save(preview_dir / preview_name)
        proc.stdin.write(im.tobytes())
        written += 1

    for i in range(counts["intro"]):
        emit(intro_frame(i, counts["intro"], args.version), "intro.png" if i == 0 else None)
    for i in range(counts["chart"]):
        emit(chart_frame(i, counts["chart"], rows, args.version), "chart.png" if i == counts["chart"]-1 else None)

    for i in range(counts["footage"]):
        t = 62.0 + i / FPS
        cap.set(cv2.CAP_PROP_POS_MSEC, t*1000)
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f"No source frame at {t:.2f}s")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        three = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        runtime_conf = 0.70 if args.version == "v3" else 0.35
        result = model.predict(three, imgsz=416, conf=runtime_conf, iou=0.7, verbose=False)[0]
        rats = [b for b in result.boxes if int(b.cls.item()) == 0]
        best = max(rats, key=lambda b: float(b.conf.item())) if rats else None
        box = best.xyxy[0].tolist() if best is not None else None
        conf = float(best.conf.item()) if best is not None else None
        emit(footage_frame(frame, box, conf, args.version), "footage.png" if i == 20 else None)
    cap.release()

    for i in range(counts["close"]):
        emit(closing_frame(i, counts["close"], args.version), "closing.png" if i == 0 else None)

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg encode failed")
    assert written == total
    print(f"Wrote {out} ({total/FPS:.1f}s, {W}x{H}, {FPS}fps)")
    for p in (csv_path, model_path, CLIP, out):
        print(f"SHA256 {p.relative_to(ROOT)} {input_hash(p)}")


if __name__ == "__main__":
    main()
