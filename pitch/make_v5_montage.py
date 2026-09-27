"""Lay out saved V5 development-replay audit images; never run inference."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "pitch/assets/v5-event-stills"
OUT = ROOT / "pitch/out"
BUILD = ROOT / "pitch/.build/v5-montage"
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
NAVY = (16, 38, 53)
WHITE = (239, 248, 243)
MINT = (174, 229, 210)
MUTED = (181, 203, 199)
PANELS = [
    ("new_room_014327", "New-room moving plush", "saved event 1 · confidence .790"),
    ("new_room_014605", "New-room parked plush", "saved event 1 · confidence .927"),
    ("zoom15_b", "Earlier metal table", "saved event 1 · confidence .952"),
    ("table_c", "Earlier floor clip", "saved event 1 · confidence .824"),
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(BOLD if bold else FONT, size)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (1280, 720), NAVY)
    return image, ImageDraw.Draw(image)


def make_panel(index: int, clip: str, name: str, detail: str) -> tuple[Path, Path]:
    source = SOURCE / f"{clip}-event_0001_full_crop.jpg"
    image, draw = base()
    draw.text((80, 24), "BARN OWL  /  V5 DETECTOR", font=font(26, True), fill=MINT)
    draw.text((80, 65), name, font=font(38, True), fill=WHITE)
    draw.text((1190, 72), f"{index}/4", font=font(22), fill=MUTED)
    with Image.open(source) as src:
        evidence = src.convert("RGB").resize((960, 540), Image.Resampling.LANCZOS)
    image.paste(evidence, (160, 118))
    draw.text((80, 672), f"Recorded development replay  •  {detail}  •  room-lit plush", font=font(24), fill=MUTED)
    dest = BUILD / f"panel-{index:02d}.png"
    image.save(dest)
    return dest, source


def make_end() -> Path:
    image, draw = base()
    draw.text((80, 65), "V5 development check", font=font(57, True), fill=WHITE)
    draw.line((80, 150, 1200, 150), fill=(8, 126, 131), width=4)
    draw.text((80, 205), "0.961 rat AP50 on the weakest tuned clip", font=font(39, True), fill=MINT)
    draw.text((80, 275), "0.975 combined rat AP50 on 146 development frames", font=font(32), fill=WHITE)
    draw.text((80, 385), "V4 new-room test: 0.883, below the 0.90 target", font=font(30), fill=WHITE)
    draw.text((80, 450), "Independent fresh V5 test pending", font=font(35, True), fill=MINT)
    draw.text((80, 590), "Saved event stills; no live-positive, IR, or wild-rat validation", font=font(25), fill=MUTED)
    dest = BUILD / "panel-05.png"
    image.save(dest)
    return dest


def main() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    sources = []
    for idx, (clip, name, detail) in enumerate(PANELS, 1):
        _, source = make_panel(idx, clip, name, detail)
        sources.append(source)
    make_end()
    preview = OUT / "barn-owl-v5-development-replay-montage-v1-preview.jpg"
    with Image.open(BUILD / "panel-01.png") as image:
        image.save(preview, quality=92, subsampling=0)
    concat = BUILD / "concat.txt"
    lines = []
    for idx in range(1, 6):
        lines.extend((f"file '{BUILD / f'panel-{idx:02d}.png'}'", "duration 2.4"))
    lines.append(f"file '{BUILD / 'panel-05.png'}'")
    concat.write_text("\n".join(lines) + "\n")
    video = OUT / "barn-owl-v5-development-replay-montage-v1.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat),
        "-vf", "fps=24,format=yuv420p", "-c:v", "libx264", "-crf", "20",
        "-movflags", "+faststart", str(video),
    ], check=True)
    print(json.dumps({
        "video": str(video), "bytes": video.stat().st_size, "sha256": sha256(video),
        "preview": str(preview),
        "sources": {str(path.relative_to(ROOT)): sha256(path) for path in sources},
    }, indent=2))


if __name__ == "__main__":
    main()
