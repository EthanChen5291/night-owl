#!/usr/bin/env python3
"""Extract frames from the phone (or rig) clips into ``frames/<tag>_<n>.jpg``.

Input is a directory of clips (``clips/*.MOV`` by default). Each clip needs a tag, which is the
unit the val split is made on later (``make_dataset.py`` splits by tag, never by frame). Two ways
to get one:

- ``--tags clips.csv`` with header ``filename,tag`` (``IMG_7777.MOV,bed_a``); this is the recommended
  path because the IMG_ names from the phone say nothing about the scene;
- ``--tag-from-name`` uses the clip's stem, lowercased, for clips that were renamed already.

Clips with no tag are skipped and listed at the end. Frames are sampled at ``--fps`` (3 by
default), downscaled so the long side is at most ``--max-side`` (960; 0 keeps the 1080p source) and
numbered continuously per tag, so two clips with the same tag just extend the sequence.

The default backend shells out to ``ffmpeg`` (it honours the phone's rotation metadata and is fast);
``--backend cv2`` is the fallback when ffmpeg is missing. A ``frames/_sources.csv`` (frame, clip,
t_sec) is written either way so a frame can be traced back to a moment in a clip.

Example::

    python3 extract_frames.py --clips clips --tags clips.csv --fps 3 --max-side 960
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

from common import IMG_EXTS, append_csv_row, index_of, list_frames, tag_of

CLIP_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".h264"}
SOURCES_FIELDS = ["frame", "clip", "t_sec"]


def load_tag_map(csv_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with csv_path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            fn = (row.get("filename") or "").strip()
            tag = (row.get("tag") or "").strip()
            if fn and tag:
                out[fn] = tag
                out[Path(fn).stem] = tag
    return out


def next_index(frames_dir: Path, tag: str) -> int:
    """Continue numbering after whatever is already there for this tag."""
    idx = [index_of(f.stem) for f in list_frames(frames_dir) if tag_of(f.stem) == tag]
    return (max(idx) + 1) if idx else 0


def scale_filter(max_side: int) -> str:
    if max_side <= 0:
        return ""
    # keep aspect, only shrink, even dimensions for the jpeg encoder
    return (f"scale=w='if(gt(iw,ih),min(iw,{max_side}),-2)'"
            f":h='if(gt(iw,ih),-2,min(ih,{max_side}))'")


def extract_ffmpeg(clip: Path, out_dir: Path, tag: str, fps: float, max_side: int, start: int) -> list[Path]:
    vf = f"fps={fps}"
    sf = scale_filter(max_side)
    if sf:
        vf += "," + sf
    pattern = out_dir / f"{tag}_%05d.jpg"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(clip),
           "-vf", vf, "-q:v", "2", "-start_number", str(start), str(pattern)]
    subprocess.run(cmd, check=True)
    new = [f for f in list_frames(out_dir) if tag_of(f.stem) == tag and index_of(f.stem) >= start]
    return sorted(new, key=lambda f: index_of(f.stem))


def extract_cv2(clip: Path, out_dir: Path, tag: str, fps: float, max_side: int, start: int) -> list[Path]:
    import cv2  # lazy so --help works without it

    cap = cv2.VideoCapture(str(clip))
    if not cap.isOpened():
        raise RuntimeError(f"cv2 cannot open {clip}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(src_fps / fps)))
    written: list[Path] = []
    i = 0
    n = start
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            h, w = frame.shape[:2]
            if max_side > 0 and max(h, w) > max_side:
                s = max_side / max(h, w)
                frame = cv2.resize(frame, (int(w * s) // 2 * 2, int(h * s) // 2 * 2), interpolation=cv2.INTER_AREA)
            p = out_dir / f"{tag}_{n:05d}.jpg"
            cv2.imwrite(str(p), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            written.append(p)
            n += 1
        i += 1
    cap.release()
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", default="clips", help="directory of clips (default: clips/)")
    ap.add_argument("--out", default="frames", help="output frames directory (default: frames/)")
    ap.add_argument("--fps", type=float, default=3.0, help="frames per second to keep (default: 3)")
    ap.add_argument("--max-side", type=int, default=960, help="downscale so the long side <= this; 0 = keep source")
    ap.add_argument("--tags", help="clips.csv with columns filename,tag")
    ap.add_argument("--tag-from-name", action="store_true", help="use the clip stem (lowercased) as the tag")
    ap.add_argument("--backend", choices=["ffmpeg", "cv2"], default="ffmpeg" if shutil.which("ffmpeg") else "cv2")
    ap.add_argument("--only", help="comma-separated clip filenames or tags to process")
    ap.add_argument("--dry-run", action="store_true", help="list what would be extracted and exit")
    args = ap.parse_args(argv)

    clips_dir = Path(args.clips)
    out_dir = Path(args.out)
    if not clips_dir.is_dir():
        print(f"no such clips dir: {clips_dir}", file=sys.stderr)
        return 2
    clips = sorted(p for p in clips_dir.iterdir() if p.suffix.lower() in CLIP_EXTS)
    if not clips:
        print(f"no clips in {clips_dir} ({', '.join(sorted(CLIP_EXTS))})", file=sys.stderr)
        return 2

    tag_map = load_tag_map(Path(args.tags)) if args.tags else {}
    if not tag_map and not args.tag_from_name:
        print("need --tags clips.csv or --tag-from-name (a clip without a tag cannot be split correctly later)",
              file=sys.stderr)
        return 2
    only = {s.strip() for s in args.only.split(",")} if args.only else None

    out_dir.mkdir(parents=True, exist_ok=True)
    skipped: list[str] = []
    totals: dict[str, int] = {}
    for clip in clips:
        tag = tag_map.get(clip.name) or tag_map.get(clip.stem)
        if not tag and args.tag_from_name:
            tag = clip.stem.lower()
        if not tag:
            skipped.append(clip.name)
            continue
        if only and clip.name not in only and tag not in only:
            continue
        start = next_index(out_dir, tag)
        print(f"{clip.name:>16}  tag={tag:<12} start={start:<6} backend={args.backend}", end="", flush=True)
        if args.dry_run:
            print()
            continue
        fn = extract_ffmpeg if args.backend == "ffmpeg" else extract_cv2
        try:
            frames = fn(clip, out_dir, tag, args.fps, args.max_side, start)
        except Exception as e:  # noqa: BLE001 - one bad clip must not stop the batch
            print(f"  FAILED: {e}")
            skipped.append(f"{clip.name} (error)")
            continue
        for k, f in enumerate(frames):
            append_csv_row(out_dir / "_sources.csv", SOURCES_FIELDS,
                           {"frame": f.name, "clip": clip.name, "t_sec": f"{k / args.fps:.3f}"})
        totals[tag] = totals.get(tag, 0) + len(frames)
        print(f"  -> {len(frames)} frames")

    print()
    print("frames per tag:")
    for tag, n in sorted(totals.items()):
        print(f"  {tag:<14} {n}")
    print(f"  {'total':<14} {sum(totals.values())}")
    if skipped:
        print("skipped (no tag or error): " + ", ".join(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
