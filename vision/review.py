#!/usr/bin/env python3
"""Minimal OpenCV box-review tool for the auto-labels, with a written record of what was reviewed.

Shows one frame at a time with its boxes (green = rat, blue = person, yellow = selected). Every
decision is appended to ``labels/_reviewed.txt`` as ``<stem>\\t<status>\\t<iso time>`` so the next
person can tell reviewed frames from untouched ones (the handoff README complains that this was not
recorded the first time round; this file is the fix). ``autolabel.py`` never overwrites a frame
listed there.

Keys::

    n / space   next frame           p / b       previous frame
    a           accept as shown      x           mark frame empty (delete all boxes)
    d           delete selected box  D           delete all boxes (same as x)
    c           toggle class of the selected box (rat <-> person)
    tab         select next box      u           undo edits on this frame (reload from disk)
    q / esc     quit

Mouse: click inside a box to select it; click-drag on empty space draws a new rat box.
Moving away from an edited frame saves it and logs it as ``edited``; ``a``/``x`` log ``accepted`` /
``empty``. Frames only looked at are not logged, so "reviewed" really means a decision was made.

Order defaults to ``--order conf`` (lowest max rat confidence first, from ``_autolabel.csv``), which
puts the dark-floor misses and the ambiguous boxes at the front of the queue.

Example::

    python3 review.py --frames frames --labels labels --unreviewed --tag corr_d
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import CLASS_NAMES, label_path, list_frames, read_csv_rows, read_labels, tag_of, write_labels

COLORS = {0: (0, 200, 0), 1: (255, 120, 0)}
SELECTED = (0, 220, 255)
WINDOW = "review  (n/p a x d c tab u q)"


def load_reviewed(labels_dir: Path) -> dict[str, str]:
    p = labels_dir / "_reviewed.txt"
    out: dict[str, str] = {}
    if p.is_file():
        for line in p.read_text().splitlines():
            parts = line.split("\t")
            if parts and parts[0].strip():
                out[parts[0].strip()] = parts[1] if len(parts) > 1 else "?"
    return out


def log_reviewed(labels_dir: Path, stem: str, status: str) -> None:
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    with (labels_dir / "_reviewed.txt").open("a") as fh:
        fh.write(f"{stem}\t{status}\t{ts}\n")


class Reviewer:
    def __init__(self, frames, labels_dir: Path, scale: float):
        import cv2

        self.cv2 = cv2
        self.frames = frames
        self.labels_dir = labels_dir
        self.i = 0
        self.scale = scale
        self.boxes: list[list[float]] = []
        self.sel = -1
        self.dirty = False
        self.img = None
        self.drag = None  # (x0, y0, x1, y1) in display pixels
        self.reviewed = load_reviewed(labels_dir)
        cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(WINDOW, self.on_mouse)

    # ----- state -----
    def load(self):
        f = self.frames[self.i]
        self.img = self.cv2.imread(str(f))
        if self.img is None:  # unreadable file: show a black frame rather than crash mid-session
            import numpy as np
            self.img = np.zeros((480, 640, 3), dtype=np.uint8)
        self.boxes = read_labels(label_path(self.labels_dir, f))
        self.sel = 0 if self.boxes else -1
        self.dirty = False

    def save(self, status: str):
        f = self.frames[self.i]
        write_labels(label_path(self.labels_dir, f), self.boxes)
        log_reviewed(self.labels_dir, f.stem, status)
        self.reviewed[f.stem] = status
        self.dirty = False

    def leave(self):
        if self.dirty:
            self.save("edited")

    # ----- geometry -----
    def disp_size(self):
        h, w = self.img.shape[:2]
        return int(w * self.scale), int(h * self.scale)

    def box_px(self, b):
        dw, dh = self.disp_size()
        _, cx, cy, w, h = b
        return (int((cx - w / 2) * dw), int((cy - h / 2) * dh), int((cx + w / 2) * dw), int((cy + h / 2) * dh))

    def on_mouse(self, event, x, y, flags, param):
        cv2 = self.cv2
        if event == cv2.EVENT_LBUTTONDOWN:
            hit = -1
            for k, b in enumerate(self.boxes):
                x0, y0, x1, y1 = self.box_px(b)
                if x0 <= x <= x1 and y0 <= y <= y1:
                    hit = k
            if hit >= 0:
                self.sel = hit
                self.drag = None
            else:
                self.drag = [x, y, x, y]
        elif event == cv2.EVENT_MOUSEMOVE and self.drag is not None:
            self.drag[2], self.drag[3] = x, y
        elif event == cv2.EVENT_LBUTTONUP and self.drag is not None:
            x0, y0, x1, y1 = self.drag
            self.drag = None
            dw, dh = self.disp_size()
            if abs(x1 - x0) > 6 and abs(y1 - y0) > 6:
                xa, xb = sorted((x0, x1))
                ya, yb = sorted((y0, y1))
                self.boxes.append([0, (xa + xb) / 2 / dw, (ya + yb) / 2 / dh, (xb - xa) / dw, (yb - ya) / dh])
                self.sel = len(self.boxes) - 1
                self.dirty = True

    # ----- drawing -----
    def render(self):
        cv2 = self.cv2
        dw, dh = self.disp_size()
        view = cv2.resize(self.img, (dw, dh)) if self.scale != 1.0 else self.img.copy()
        for k, b in enumerate(self.boxes):
            x0, y0, x1, y1 = self.box_px(b)
            col = SELECTED if k == self.sel else COLORS.get(int(b[0]), (200, 200, 200))
            cv2.rectangle(view, (x0, y0), (x1, y1), col, 2)
            cv2.putText(view, CLASS_NAMES[int(b[0])] if int(b[0]) < 2 else str(b[0]), (x0, max(12, y0 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
        if self.drag is not None:
            x0, y0, x1, y1 = self.drag
            cv2.rectangle(view, (x0, y0), (x1, y1), SELECTED, 1)
        f = self.frames[self.i]
        status = self.reviewed.get(f.stem, "-")
        hud = f"{self.i + 1}/{len(self.frames)}  {f.name}  boxes={len(self.boxes)}  reviewed={status}" + \
              ("  *edited*" if self.dirty else "")
        cv2.rectangle(view, (0, 0), (dw, 22), (0, 0, 0), -1)
        cv2.putText(view, hud, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.imshow(WINDOW, view)

    # ----- loop -----
    def run(self) -> int:
        cv2 = self.cv2
        self.load()
        while True:
            self.render()
            k = cv2.waitKey(30) & 0xFF
            if k == 255:
                continue
            ch = chr(k) if k < 128 else ""
            if ch in ("q",) or k == 27:
                self.leave()
                break
            elif ch in ("n", " "):
                self.leave()
                if self.i < len(self.frames) - 1:
                    self.i += 1
                    self.load()
            elif ch in ("p", "b"):
                self.leave()
                if self.i > 0:
                    self.i -= 1
                    self.load()
            elif ch == "a":
                self.save("accepted")
                if self.i < len(self.frames) - 1:
                    self.i += 1
                    self.load()
            elif ch in ("x", "D"):
                self.boxes = []
                self.sel = -1
                self.save("empty")
                if self.i < len(self.frames) - 1:
                    self.i += 1
                    self.load()
            elif ch == "d" and 0 <= self.sel < len(self.boxes):
                del self.boxes[self.sel]
                self.sel = min(self.sel, len(self.boxes) - 1)
                self.dirty = True
            elif ch == "c" and 0 <= self.sel < len(self.boxes):
                self.boxes[self.sel][0] = 1 - int(self.boxes[self.sel][0])
                self.dirty = True
            elif k == 9 and self.boxes:  # tab
                self.sel = (self.sel + 1) % len(self.boxes)
            elif ch == "u":
                self.load()
        cv2.destroyAllWindows()
        return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", default="frames")
    ap.add_argument("--labels", default="labels")
    ap.add_argument("--tag", help="only frames of this tag (comma-separated for several)")
    ap.add_argument("--unreviewed", action="store_true", help="skip frames already in _reviewed.txt")
    ap.add_argument("--with-boxes", action="store_true", help="only frames that currently have boxes")
    ap.add_argument("--order", choices=["name", "conf"], default="conf",
                    help="conf = lowest max rat confidence first (needs _autolabel.csv), name = by tag/index")
    ap.add_argument("--start", type=int, default=0, help="start at this position in the queue")
    ap.add_argument("--scale", type=float, default=1.0, help="display scale (0.6 for a small laptop screen)")
    ap.add_argument("--stats", action="store_true", help="print review status counts and exit (no window)")
    args = ap.parse_args(argv)

    frames_dir, labels_dir = Path(args.frames), Path(args.labels)
    frames = list_frames(frames_dir)
    reviewed = load_reviewed(labels_dir)
    if args.stats:
        by = {}
        for s in reviewed.values():
            by[s] = by.get(s, 0) + 1
        n_rev = sum(1 for f in frames if f.stem in reviewed)
        print(f"frames: {len(frames)}  reviewed: {n_rev} ({100 * n_rev / max(1, len(frames)):.0f}%)  "
              f"by status: {by}")
        return 0
    if args.tag:
        tags = {t.strip() for t in args.tag.split(",")}
        frames = [f for f in frames if tag_of(f.stem) in tags]
    if args.unreviewed:
        frames = [f for f in frames if f.stem not in reviewed]
    if args.with_boxes:
        frames = [f for f in frames if read_labels(label_path(labels_dir, f))]
    if args.order == "conf":
        conf = {r["frame"]: float(r.get("max_conf_rat") or 0) for r in read_csv_rows(labels_dir / "_autolabel.csv")}
        frames.sort(key=lambda f: (conf.get(f.name, 0.0), f.name))
    if not frames:
        print("nothing to review")
        return 0
    try:
        import cv2  # noqa: F401
    except ImportError:
        print("opencv-python is needed for the viewer: pip install opencv-python", file=sys.stderr)
        return 2
    r = Reviewer(frames, labels_dir, args.scale)
    r.i = max(0, min(args.start, len(frames) - 1))
    return r.run()


if __name__ == "__main__":
    sys.exit(main())
