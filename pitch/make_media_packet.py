"""Assemble a room-lit review sheet from existing labels and saved V4 events.

This script does no model inference. It only draws reviewed YOLO labels on
existing source frames and lays out saved replay audit sheets without changing
their underlying pixels.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "pitch/media-v4"
FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
NAVY = (16, 38, 53)
INK = (235, 248, 243)
MUTED = (177, 203, 199)
GREEN = (37, 220, 128)
RED = (231, 91, 86)

MANUAL = [
    ("new_room_014327_00014", "Moving plush", "Reviewed rat box"),
    ("new_room_014605_00020", "Parked plush", "Reviewed rat and person boxes"),
    ("new_room_020101_00090", "People only", "Reviewed person boxes; no plush"),
]
PREDICTIONS = [
    ("event_0003_full_crop.jpg", "Moving plush", "V4 recorded event · conf .800"),
    ("event_0010_full_crop.jpg", "Plush near person", "V4 recorded event · conf .726"),
    ("event_0001_full_crop.jpg", "Dark case false alert", "V4 recorded event · conf .755"),
]
AUDIT_REL = Path("vision/runs/modal-rat-v4-20260926/new_room_final_once/replay/new_room_014327/audit_sheets")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def draw_reviewed_frame(source_root: Path, stem: str, dst: Path) -> tuple[Path, Path]:
    frame = source_root / "vision/new_room_test/frames" / f"{stem}.jpg"
    labels = source_root / "vision/new_room_test/labels" / f"{stem}.txt"
    im = Image.open(frame).convert("RGB")
    d = ImageDraw.Draw(im)
    w, h = im.size
    for row in labels.read_text().splitlines():
        cls, xc, yc, bw, bh = row.split()
        xc, yc, bw, bh = map(float, (xc, yc, bw, bh))
        xy = ((xc-bw/2)*w, (yc-bh/2)*h, (xc+bw/2)*w, (yc+bh/2)*h)
        d.rectangle(xy, outline=GREEN if cls == "0" else RED, width=4)
    im.save(dst, quality=94, subsampling=0)
    return frame, labels


def fitted(im: Image.Image, max_w: int, max_h: int) -> Image.Image:
    out = im.copy()
    out.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root", type=Path, default=ROOT,
        help="Repository root or extracted evaluation ZIP directory containing vision/",
    )
    source_root = parser.parse_args().source_root.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    panels: list[tuple[Path, str, str, str]] = []
    sources: list[Path] = []
    for stem, title, detail in MANUAL:
        target = OUT / f"manual-{stem}.jpg"
        frame, labels = draw_reviewed_frame(source_root, stem, target)
        panels.append((target, "REVIEWED LABEL", title, detail))
        sources += [frame, labels]
    for fname, title, detail in PREDICTIONS:
        source = source_root / AUDIT_REL / fname
        target = OUT / f"v4-{fname}"
        shutil.copyfile(source, target)
        panels.append((target, "MODEL PREDICTION", title, detail))
        sources.append(source)

    pw, ph, gutter = 620, 520, 20
    width = 3*pw + 4*gutter
    header, footer = 122, 158
    height = header + 2*ph + 3*gutter + footer
    sheet = Image.new("RGB", (width, height), NAVY)
    d = ImageDraw.Draw(sheet)
    d.text((gutter, 22), "Barn Owl  |  room-lit plush review", font=font(49, True), fill=INK)
    d.text((gutter, 80), "Top: agent-reviewed labels    Bottom: locked V4 recorded-video event outputs", font=font(27), fill=MUTED)

    for idx, (path, kind, title, detail) in enumerate(panels):
        col, row = idx % 3, idx // 3
        x = gutter + col*(pw+gutter)
        y = header + gutter + row*(ph+gutter)
        d.rectangle((x, y, x+pw, y+ph), fill=(248, 249, 245))
        src = Image.open(path).convert("RGB")
        img = fitted(src, pw-20, 405)
        sheet.paste(img, (x+(pw-img.width)//2, y+12+(405-img.height)//2))
        d.text((x+14, y+425), kind, font=font(17, True), fill=(0, 124, 129))
        d.text((x+14, y+451), title, font=font(27, True), fill=NAVY)
        d.text((x+14, y+486), detail, font=font(19), fill=(67, 87, 92))

    fy = header + 2*ph + 3*gutter + 15
    d.text((gutter, fy), "New-room test limit", font=font(30, True), fill=INK)
    d.text((gutter, fy+42), "Moving clip: 9 plush events and 1 false case alert. Parked plush: 0 events. People-only: 0 events over 181 s.", font=font(22), fill=MUTED)
    d.text((gutter, fy+75), "No IR, wild-rat, or live-Pi positive detection claim. AP50 .883 on 439 reviewed frames is below the .90 target.", font=font(22), fill=MUTED)
    d.text((gutter, fy+108), "Green boxes: rat; red boxes: person. Top boxes are manual labels; bottom boxes and crops are saved V4 outputs.", font=font(21), fill=MUTED)
    output = OUT / "room-lit-review-contact-sheet.jpg"
    sheet.save(output, quality=91, subsampling=0)
    print(f"Wrote {output} {sheet.size}")
    for p in sources + [output]:
        try:
            label = p.relative_to(source_root)
        except ValueError:
            label = p.relative_to(ROOT)
        print(f"SHA256 {label} {sha256(p)}")


if __name__ == "__main__":
    main()
