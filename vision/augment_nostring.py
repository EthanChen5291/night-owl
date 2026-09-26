#!/usr/bin/env python3
"""Paste-augmentation that hides the prop's control string, plus plain photometric augmentation.

The prop is pulled across the floor on a thin string. In the phone footage the string is visible in
a lot of positives, and a detector fine-tuned on 3k frames will happily learn "thin bright line above
a dark blob" as the rat. On stage the string is also there, but the point of this script is to stop
the model *needing* it, because rig frames (IR, top-down) show it differently or not at all.

For every frame with at least one rat box:

1. cut the rat box out of the source frame with a small margin;
2. ``--inpaint``: mask a narrow vertical strip where the string enters the box (centred on the box,
   from ``--string-above`` px above the top edge down to ``--string-depth`` of the box height) and
   ``cv2.inpaint`` it away before cutting; the strip stays inside the pasted crop so the paste
   carries no string at all;
3. paste the crop ``--per-frame`` times onto random *negative* frames (frames whose label file is
   empty, or ``--negatives DIR``) with random scale (``--scale``), horizontal flip, brightness and
   contrast jitter, a feathered edge so the seam is soft, and a position whose centre y is below
   ``--floor-y`` so the placement agrees with the floor rule the Pi applies;
4. ``--photometric N``: also write N photometric-only copies of the source frame (gamma, noise,
   blur, gain) with the original boxes, which is the cheap way to widen the IR exposure domain.

Output goes to ``frames_aug/`` and ``labels_aug/``; frame names are ``<srctag>_aug_<n>.jpg`` so
``make_dataset.py`` can trace an augmented frame back to its clips (``labels_aug/_sources.csv``
records the rat-source and background-source tags) and keep it out of any split that contains
either. Never point ``--negatives`` at val-tag frames if you can help it, and never review these
files: they are generated, delete and regenerate instead.

Example::

    python3 augment_nostring.py --per-frame 2 --photometric 1 --inpaint --seed 0
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from common import append_csv_row, label_path, list_frames, read_labels, tag_of, write_labels

SOURCES_FIELDS = ["frame", "kind", "rat_source", "bg_source"]


def inpaint_string(img, box_px, above: int, depth: float, width_frac: float, cv2, np):
    """Remove a thin vertical strip above/into the top of the box (where the string attaches)."""
    x0, y0, x1, y1 = box_px
    h, w = img.shape[:2]
    bw, bh = x1 - x0, y1 - y0
    sw = max(3, int(bw * width_frac))
    cx = (x0 + x1) // 2
    mask = np.zeros((h, w), dtype=np.uint8)
    ya = max(0, y0 - above)
    yb = min(h, int(y0 + bh * depth))
    mask[ya:yb, max(0, cx - sw // 2): min(w, cx + sw // 2 + 1)] = 255
    return cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)


def photometric(img, rng: random.Random, cv2, np, strength: float = 1.0):
    """Gain, bias, gamma, noise, blur. ``strength`` scales the ranges (0.5 = half as wild)."""
    out = img.astype(np.float32)
    gain = rng.uniform(1 - 0.4 * strength, 1 + 0.4 * strength)
    bias = rng.uniform(-25 * strength, 25 * strength)
    out = out * gain + bias
    gamma = rng.uniform(1 - 0.3 * strength, 1 + 0.4 * strength)
    out = 255.0 * np.power(np.clip(out, 0, 255) / 255.0, gamma)
    if rng.random() < 0.5:
        out = out + np.random.default_rng(rng.randrange(1 << 30)).normal(0, rng.uniform(2, 8), out.shape)
    out = np.clip(out, 0, 255).astype(np.uint8)
    if rng.random() < 0.3:
        k = rng.choice([3, 5])
        out = cv2.GaussianBlur(out, (k, k), 0)
    return out


def feather_mask(h: int, w: int, cv2, np):
    m = np.zeros((h, w), dtype=np.float32)
    bx, by = max(2, w // 10), max(2, h // 10)
    m[by:h - by, bx:w - bx] = 1.0
    k = max(3, (min(bx, by) * 2) | 1)
    m = cv2.GaussianBlur(m, (k, k), 0)
    return m[..., None]


def paste(bg, crop, rng: random.Random, scale, floor_y: float, cv2, np):
    """Return (image, [cls, cx, cy, w, h]) or None if the crop does not fit."""
    H, W = bg.shape[:2]
    s = rng.uniform(*scale)
    ch, cw = crop.shape[:2]
    nw, nh = max(8, int(cw * s)), max(8, int(ch * s))
    if nw >= W * 0.9 or nh >= H * 0.9:
        s = min(W * 0.5 / cw, H * 0.5 / ch)
        nw, nh = max(8, int(cw * s)), max(8, int(ch * s))
    c = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    if rng.random() < 0.5:
        c = cv2.flip(c, 1)
    y_min = int(max(0, floor_y * H - nh / 2))
    if y_min + nh >= H or nw >= W:
        return None
    x0 = rng.randint(0, W - nw - 1)
    y0 = rng.randint(y_min, H - nh - 1)
    out = bg.copy()
    roi = out[y0:y0 + nh, x0:x0 + nw].astype(np.float32)
    # match the crop's border brightness to the landing patch so the seam is not a rectangle of
    # different exposure (the crop's own floor vs the background's floor), then jitter mildly
    bx, by = max(1, nw // 10), max(1, nh // 10)
    ring = np.ones((nh, nw), dtype=bool)
    ring[by:nh - by, bx:nw - bx] = False
    # robust: the ring is floor plus some prop, the floor is the brighter majority under IR
    gain = float(np.clip(np.median(roi) / max(1.0, float(np.percentile(c[ring], 75))), 0.5, 2.0))
    c = np.clip(c.astype(np.float32) * gain, 0, 255).astype(np.uint8)
    c = photometric(c, rng, cv2, np, strength=0.5)
    m = feather_mask(nh, nw, cv2, np)
    out[y0:y0 + nh, x0:x0 + nw] = (roi * (1 - m) + c.astype(np.float32) * m).astype(np.uint8)
    box = [0, (x0 + nw / 2) / W, (y0 + nh / 2) / H, nw / W, nh / H]
    return out, box


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", default="frames")
    ap.add_argument("--labels", default="labels")
    ap.add_argument("--negatives", help="directory of background frames (default: frames with an empty label file)")
    ap.add_argument("--out-frames", default="frames_aug")
    ap.add_argument("--out-labels", default="labels_aug")
    ap.add_argument("--per-frame", type=int, default=2, help="pastes per positive frame (0 disables pasting)")
    ap.add_argument("--photometric", type=int, default=1, help="photometric-only copies per positive frame")
    ap.add_argument("--inpaint", action="store_true", help="inpaint the string strip before cutting the crop")
    ap.add_argument("--string-above", type=int, default=40, help="px above the box top to inpaint")
    ap.add_argument("--string-depth", type=float, default=0.25, help="fraction of box height below the top edge to inpaint")
    ap.add_argument("--string-width", type=float, default=0.06, help="strip width as a fraction of box width")
    ap.add_argument("--margin", type=float, default=0.05, help="crop margin as a fraction of the box")
    ap.add_argument("--scale", default="0.6,1.4", help="random scale range for pastes")
    ap.add_argument("--floor-y", type=float, default=0.40, help="paste centre y must be below this (matches detect.py FLOOR_Y)")
    ap.add_argument("--exclude-tags", default="", help="comma-separated tags never used as rat or background source (your val tags)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N positive frames")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--clean", action="store_true", help="delete existing output first")
    args = ap.parse_args(argv)

    try:
        import cv2
        import numpy as np
    except ImportError:
        print("needs opencv-python and numpy", file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    scale = tuple(float(v) for v in args.scale.split(","))
    excl = {t.strip() for t in args.exclude_tags.split(",") if t.strip()}
    frames_dir, labels_dir = Path(args.frames), Path(args.labels)
    out_f, out_l = Path(args.out_frames), Path(args.out_labels)
    if args.clean:
        for d in (out_f, out_l):
            if d.is_dir():
                for p in d.iterdir():
                    p.unlink()
    out_f.mkdir(parents=True, exist_ok=True)
    out_l.mkdir(parents=True, exist_ok=True)

    frames = [f for f in list_frames(frames_dir) if tag_of(f.stem) not in excl]
    positives, negatives = [], []
    for f in frames:
        boxes = read_labels(label_path(labels_dir, f))
        rats = [b for b in boxes if int(b[0]) == 0]
        if rats:
            positives.append((f, boxes, rats))
        elif label_path(labels_dir, f).is_file() and not boxes:
            negatives.append(f)
    if args.negatives:
        negatives = [f for f in list_frames(args.negatives) if tag_of(f.stem) not in excl]
    if args.limit:
        positives = positives[: args.limit]
    print(f"{len(positives)} positive frames, {len(negatives)} negative backgrounds, excluded tags: {sorted(excl) or '-'}")
    if not positives or (args.per_frame and not negatives):
        print("nothing to do (need positives, and negatives for pasting)")
        return 0

    n_paste = n_photo = 0
    counter: dict[str, int] = {}
    for f, boxes, rats in positives:
        src_tag = tag_of(f.stem)
        img = cv2.imread(str(f))
        if img is None:
            continue
        H, W = img.shape[:2]

        def new_name(kind: str) -> str:
            counter[src_tag] = counter.get(src_tag, 0) + 1
            return f"{src_tag}_aug_{counter[src_tag]:05d}"

        # photometric copies keep every box
        for _ in range(args.photometric):
            stem = new_name("photo")
            cv2.imwrite(str(out_f / f"{stem}.jpg"), photometric(img, rng, cv2, np), [cv2.IMWRITE_JPEG_QUALITY, 90])
            write_labels(out_l / f"{stem}.txt", boxes)
            append_csv_row(out_l / "_sources.csv", SOURCES_FIELDS,
                           {"frame": f"{stem}.jpg", "kind": "photometric", "rat_source": src_tag, "bg_source": src_tag})
            n_photo += 1

        # paste copies: one rat crop (the largest) onto a random negative
        b = max(rats, key=lambda r: r[3] * r[4])
        _, cx, cy, w, h = b
        mx, my = w * args.margin, h * args.margin
        x0, y0 = int(max(0, (cx - w / 2 - mx) * W)), int(max(0, (cy - h / 2 - my) * H))
        x1, y1 = int(min(W, (cx + w / 2 + mx) * W)), int(min(H, (cy + h / 2 + my) * H))
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        src = img
        if args.inpaint:
            src = inpaint_string(img, (x0, y0, x1, y1), args.string_above, args.string_depth, args.string_width, cv2, np)
        crop = src[y0:y1, x0:x1]
        for _ in range(args.per_frame):
            bgf = rng.choice(negatives)
            bg = cv2.imread(str(bgf))
            if bg is None:
                continue
            r = paste(bg, crop, rng, scale, args.floor_y, cv2, np)
            if r is None:
                continue
            out_img, box = r
            stem = new_name("paste")
            cv2.imwrite(str(out_f / f"{stem}.jpg"), out_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            write_labels(out_l / f"{stem}.txt", [box])
            append_csv_row(out_l / "_sources.csv", SOURCES_FIELDS,
                           {"frame": f"{stem}.jpg", "kind": "paste", "rat_source": src_tag, "bg_source": tag_of(bgf.stem)})
            n_paste += 1

    print(f"wrote {n_paste} paste frames and {n_photo} photometric frames to {out_f}/ (+ labels in {out_l}/)")
    print("next: make_dataset.py --extra frames_aug:labels_aug --val-tags ...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
