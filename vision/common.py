"""Shared helpers for the Mac-side vision scripts (frames, YOLO txt labels, clip tags).

Conventions used by every script in this directory:

- a frame is ``frames/<tag>_<n>.jpg``; ``<tag>`` is the clip tag (``bed_a``, ``stair_e`` ...) and
  ``<n>`` is a zero-padded running index within that tag;
- a label is ``labels/<same stem>.txt`` in YOLO format, one ``cls cx cy w h`` line per box, all
  normalised 0-1; class 0 = rat (the prop), 1 = person; an empty file means "reviewed, no boxes";
- files whose stem starts with ``_`` (``_autolabel.csv``, ``_reviewed.txt``) are bookkeeping, not data.

Nothing here imports cv2 or numpy so ``--help`` works on a bare interpreter.
"""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Iterable

IMG_EXTS = {".jpg", ".jpeg", ".png"}
CLASS_NAMES = ["rat", "person"]

_TAG_RE = re.compile(r"^(?P<tag>.+?)_(?P<idx>\d+)$")


def tag_of(stem: str) -> str:
    """``bed_a_0042`` -> ``bed_a``; ``bed_a_aug_0003`` -> ``bed_a_aug``; no index -> whole stem."""
    m = _TAG_RE.match(stem)
    return m.group("tag") if m else stem


def index_of(stem: str) -> int:
    m = _TAG_RE.match(stem)
    return int(m.group("idx")) if m else -1


def source_tag(tag: str) -> str:
    """Strip the ``_aug`` suffix that augment_nostring.py adds, so leak checks see the real clip."""
    return tag[:-4] if tag.endswith("_aug") else tag


def list_frames(frames_dir: str | os.PathLike) -> list[Path]:
    p = Path(frames_dir)
    if not p.is_dir():
        return []
    out = [f for f in p.iterdir() if f.suffix.lower() in IMG_EXTS and not f.name.startswith("_")]
    return sorted(out, key=lambda f: (tag_of(f.stem), index_of(f.stem), f.name))


def label_path(labels_dir: str | os.PathLike, frame: Path) -> Path:
    return Path(labels_dir) / (frame.stem + ".txt")


def read_labels(path: str | os.PathLike) -> list[list[float]]:
    """Return ``[[cls, cx, cy, w, h], ...]``; a missing file returns ``[]`` like an empty one."""
    p = Path(path)
    if not p.is_file():
        return []
    boxes = []
    for line in p.read_text().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            boxes.append([int(float(parts[0]))] + [float(v) for v in parts[1:5]])
        except ValueError:
            continue
    return boxes


def write_labels(path: str | os.PathLike, boxes: Iterable[Iterable[float]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for b in boxes:
        c, cx, cy, w, h = b[:5]
        cx, cy, w, h = (min(max(float(v), 0.0), 1.0) for v in (cx, cy, w, h))
        lines.append(f"{int(c)} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    p.write_text("\n".join(lines) + ("\n" if lines else ""))


def read_csv_rows(path: str | os.PathLike) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        return []
    with p.open(newline="") as fh:
        return list(csv.DictReader(fh))


def append_csv_row(path: str | os.PathLike, fieldnames: list[str], row: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.is_file() or p.stat().st_size == 0
    with p.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        if new:
            w.writeheader()
        w.writerow(row)


def parse_tag_list(s: str | None) -> list[str]:
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]
