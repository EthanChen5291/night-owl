#!/usr/bin/env -S uv run --with google-genai --with pillow python
"""render_node.py: product renders of the Barn Owl node (SB-01) with Gemini, from the OpenSCAD previews.

    ./renders/render_node.py --shot hero
    ./renders/render_node.py --shot situ --n 2
    ./renders/render_node.py --prompt "..." --ref enclosure/preview/d3_iso.png --out renders/node/test.png
    ./renders/render_node.py --shot top --dry-run          # print the request, no network

Reads GEMINI_API_KEY from .env (cwd, repo root, ~/divMap/.env) or the environment. The reference
images are the OpenSCAD previews in ~/div-hacks-26/enclosure/preview (pass them with --ref; by
default the tool looks for <shot>-appropriate files under --preview-dir). Outputs are PNGs under
renders/node/, which is gitignored: the deck set (hero, situ, top, variants-sheet, concepts-sheet)
is copied up to renders/ by hand once chosen.

The cyan band glow in hero/situ is a demo-only touch. A field node is dark.
"""

import argparse
import base64
import glob
import mimetypes
import os
import sys
import time

MODEL = "gemini-3-pro-image"
NODE_ID = "SB-01"
DEFAULT_PREVIEW_DIR = os.path.expanduser("~/div-hacks-26/enclosure/preview")

# ---------------------------------------------------------------- the node, in words
# Everything Gemini needs to know that the preview PNGs do not show (materials, scale, context).

BODY_D3 = (
    "Barn Owl node SB-01: a small face-down sensor box, 95 x 99 x 49 mm, matte light-grey PETG. "
    "The bottom face is a frosted translucent tray holding a camera lens, a small PIR dome and an IR "
    "LED window, all flush; the lower 12 mm of the box is a frosted band that runs all the way round. "
    "The top is a 1 mm clear lid through which a Raspberry Pi 5 board is faintly visible. An L-shaped "
    "printed arm rises from one side to a hook with a V-groove foot that sits on a round steel rail; "
    "a fan-shaped indexed sector plate at the pivot sets the tilt. Small, clean, consumer-hardware "
    "finish, no visible screws on the faces, no logos except a tiny 'SB-01' label."
)

BODY_V2 = (
    "Barn Owl node prototype: a side-facing sensor box, 107 x 96 x 45 mm, matte light-grey PETG, "
    "standing on a wedge stand tilted 20 degrees back. The front faceplate carries a camera lens, a PIR "
    "dome and an IR LED window. Consumer-hardware finish, a tiny 'SB-01' label."
)

STYLE = (
    "Photoreal product render, 50 mm lens, soft studio key light with a large gradient reflection on "
    "the lid, neutral off-white backdrop, shallow depth of field, no text overlays, no watermarks, "
    "no people. Keep the geometry exactly as in the reference images; do not add features."
)

GLOW = (
    "The frosted band emits a faint, even cyan glow (demo indicator only; keep it subtle, not neon). "
)

SHOTS = {
    "hero": {
        "body": BODY_D3,
        "prompt": "Three-quarter view from slightly below, box hanging from a short section of rail, "
                  "arm and sector plate visible. " + GLOW + STYLE,
        "refs": ["d3_assembled.png", "d3_underside.png", "hanger_assembled.png"],
        "aspect": "4:3",
    },
    "situ": {
        "body": BODY_D3,
        "prompt": "In situ, at night, on a NYC street: the node hangs face-down from the top rail of a "
                  "black cast-iron tree guard around a street-tree pit, sidewalk and a brownstone stoop "
                  "behind, a sodium-orange streetlight far off. Wet pavement, faint reflections. "
                  "The frosted band gives off a faint cyan glow that lightly tints the bark and the "
                  "soil below (demo only, keep it faint). Camera at knee height, 35 mm, slight low angle. "
                  "Photoreal, cinematic but not moody-dark: the node must read clearly. No people, no "
                  "rats, no text.",
        "refs": ["d3_assembled.png", "d3_underside.png", "hanger_assembled.png"],
        "aspect": "16:9",
    },
    "top": {
        "body": BODY_D3,
        "prompt": "Straight-down top view on the clear lid: the Raspberry Pi 5 visible through 1 mm "
                  "clear PETG, the arm leaving the frame at one side. Even light, no glow. " + STYLE,
        "refs": ["d3_assembled.png", "d3_inside.png"],
        "aspect": "1:1",
    },
    "variants-sheet": {
        "body": BODY_D3,
        "prompt": "A contact sheet of six variants of the same face-down box, 3 columns x 2 rows, each "
                  "tile labelled in small grey type D1 to D6, identical camera angle (three-quarter from "
                  "slightly below), identical lighting. D1: the whole top is frosted glass, no band. "
                  "D2: frosted upper half, opaque lower half. D3: opaque body with a 12 mm frosted band "
                  "along the bottom edge (the chosen one; mark its tile with a thin cyan outline). "
                  "D4: a thin frosted ring at mid-height. D5: frosted corners only. D6: three horizontal "
                  "frosted slots per side. " + STYLE,
        "refs": ["d3_assembled.png", "d3_underside.png"],
        "aspect": "3:2",
    },
    "concepts-sheet": {
        "body": BODY_D3,
        "prompt": "A contact sheet of five face-down mounting concepts, one row, each tile labelled in "
                  "small grey type D to H, same rail, same angle, same light. D: the rectangular box "
                  "with the frosted bottom band on an L-arm (the chosen one; thin cyan outline on its "
                  "tile). E: a short cylinder hanging from a single strap. F: a wedge-shaped body "
                  "clamped to the rail with the lens on the sloped face. G: a rounded dome with an "
                  "owl-like facial-disc recess around the lens. H: a flat puck bolted under a bracket. "
                  + STYLE,
        "refs": ["d3_assembled.png", "owl_face_angle.png"],
        "aspect": "3:1",
    },
    "face-a": {
        "body": BODY_V2,
        "prompt": "Face style A: plain frosted faceplate with three flush round windows. Three-quarter "
                  "front view. " + STYLE,
        "refs": ["v2_front.png", "v2_on_stand.png"],
        "aspect": "4:3",
    },
    "face-b": {
        "body": BODY_V2,
        "prompt": "Face style B: faceplate with a fine horizontal slotted grille, lens in a clear round "
                  "window at centre. Three-quarter front view. " + STYLE,
        "refs": ["v2_front.png", "v2_on_stand.png"],
        "aspect": "4:3",
    },
    "face-c": {
        "body": BODY_V2,
        "prompt": "Face style C: dark faceplate with a single large clear ring window around the lens, "
                  "PIR and IR behind the ring. Three-quarter front view. " + STYLE,
        "refs": ["v2_front.png", "v2_on_stand.png"],
        "aspect": "4:3",
    },
}
# D2, D4-D6, E-H and the A/B/C faceplates above are described from the README, which only pins down
# D1 (full glass top) and D3 (band). Edit freely. Ref filenames are the real ones in
# ~/div-hacks-26/enclosure/preview (listed in enclosure/MEASUREMENTS.md): d3_{assembled,cutaway,inside,
# parts,underside}, hanger_{assembled,parts}, owl_{assembled,face,face_angle,parts,tray,underside}, v2_*.


# ---------------------------------------------------------------- tiny dotenv

def load_dotenv(explicit=None):
    """Set os.environ from the first .env found. No dependency, no expansion, quotes stripped."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [explicit] if explicit else [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(here, ".env"),
        os.path.join(os.path.dirname(here), ".env"),
        os.path.expanduser("~/divMap/.env"),
    ]
    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                if key.startswith("export "):
                    key = key[7:].strip()
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    val = val[1:-1]
                os.environ.setdefault(key, val)
        return path
    return None


# ---------------------------------------------------------------- refs and output

def resolve_refs(explicit, patterns, preview_dir):
    if explicit:
        missing = [p for p in explicit if not os.path.isfile(p)]
        if missing:
            sys.exit("render_node: --ref not found: " + ", ".join(missing))
        return list(explicit)
    found = []
    for pat in patterns:
        found.extend(sorted(glob.glob(os.path.join(preview_dir, pat))))
    return list(dict.fromkeys(found))


def read_ref(path, max_px):
    """Return (bytes, mime). Downscales through Pillow when the long edge exceeds max_px."""
    mime = mimetypes.guess_type(path)[0] or "image/png"
    if max_px:
        try:
            from io import BytesIO
            from PIL import Image
            im = Image.open(path)
            if max(im.size) > max_px:
                im.thumbnail((max_px, max_px))
                buf = BytesIO()
                im.convert("RGB").save(buf, format="PNG")
                return buf.getvalue(), "image/png"
        except ImportError:
            pass
    with open(path, "rb") as f:
        return f.read(), mime


def out_paths(base, n):
    if n == 1:
        return [base]
    root, ext = os.path.splitext(base)
    return [f"{root}-{i}{ext}" for i in range(1, n + 1)]


def extract_images(response):
    """Yield raw image bytes from a generate_content response, across SDK versions."""
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in (getattr(content, "parts", None) or []):
            blob = getattr(part, "inline_data", None)
            if blob is None or not getattr(blob, "data", None):
                continue
            data = blob.data
            if isinstance(data, str):
                data = base64.b64decode(data)
            yield data


def generate(client, model, prompt, refs, aspect, out_path, timeout_s=180):
    from google.genai import types

    parts = [types.Part.from_text(text=prompt)]
    for data, mime in refs:
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))

    cfg_kwargs = {"response_modalities": ["IMAGE", "TEXT"]}
    if aspect and hasattr(types, "ImageConfig"):
        cfg_kwargs["image_config"] = types.ImageConfig(aspect_ratio=aspect)
    config = types.GenerateContentConfig(**cfg_kwargs)

    t0 = time.monotonic()
    resp = client.models.generate_content(model=model, contents=parts, config=config)
    dt = time.monotonic() - t0
    images = list(extract_images(resp))
    if not images:
        text = getattr(resp, "text", None) or "(no text)"
        raise RuntimeError(f"no image in response after {dt:.0f}s; model said: {text[:400]}")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(images[0])
    return len(images[0]), dt


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Gemini product renders of the Barn Owl node from OpenSCAD previews.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog="shots: " + ", ".join(SHOTS),
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--shot", choices=sorted(SHOTS), help="a named deck shot")
    g.add_argument("--prompt", help="free prompt (the D3 body description is prepended unless --raw)")
    ap.add_argument("--raw", action="store_true", help="with --prompt: send it verbatim, no body preamble")
    ap.add_argument("--ref", action="append", default=[], metavar="PNG",
                    help="reference image (repeatable); default: the shot's preview patterns")
    ap.add_argument("--preview-dir", default=DEFAULT_PREVIEW_DIR, help="where the OpenSCAD previews live")
    ap.add_argument("--out", help="output PNG (default renders/node/<shot>.png next to this script)")
    ap.add_argument("--n", type=int, default=1, help="how many renders (suffixed -1, -2, ...)")
    ap.add_argument("--aspect", help="aspect ratio override, e.g. 16:9")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--max-ref", type=int, default=1536, help="downscale refs above this long edge (0 = never)")
    ap.add_argument("--env", help="explicit .env path")
    ap.add_argument("--dry-run", action="store_true", help="print the request and exit, no network")
    args = ap.parse_args(argv)

    if not args.shot and not args.prompt:
        ap.error("give --shot NAME or --prompt TEXT")

    here = os.path.dirname(os.path.abspath(__file__))
    if args.shot:
        shot = SHOTS[args.shot]
        prompt = shot["body"] + " " + shot["prompt"]
        patterns = shot["refs"]
        aspect = args.aspect or shot.get("aspect")
        name = args.shot
    else:
        prompt = args.prompt if args.raw else BODY_D3 + " " + args.prompt
        patterns = ["d3_*.png"]
        aspect = args.aspect
        name = "custom"

    out_base = args.out or os.path.join(here, "node", f"{name}.png")
    outs = out_paths(out_base, max(args.n, 1))
    ref_paths = resolve_refs(args.ref, patterns, args.preview_dir)

    env_file = load_dotenv(args.env)
    key = os.environ.get("GEMINI_API_KEY")

    if args.dry_run:
        print(f"model:    {args.model}")
        print(f"shot:     {name}")
        print(f"aspect:   {aspect or '(model default)'}")
        print(f"api key:  {'found (' + key[:4] + '...' + key[-4:] + ')' if key else 'MISSING'}"
              f"{'  from ' + env_file if env_file else ''}")
        print(f"refs ({len(ref_paths)}):" + ("" if ref_paths else "  none found; pass --ref or fix --preview-dir"))
        for p in ref_paths:
            size = os.path.getsize(p) / 1024
            print(f"  {p}  ({size:.0f} KB)")
        print(f"out:      " + ", ".join(outs))
        print("prompt:")
        print("  " + prompt)
        return 0

    if not key:
        sys.exit("render_node: GEMINI_API_KEY not set; put it in .env or the environment")
    if not ref_paths:
        print("render_node: warning: no reference images; the model will invent the geometry", file=sys.stderr)

    from google import genai
    client = genai.Client(api_key=key)
    refs = [read_ref(p, args.max_ref) for p in ref_paths]

    rc = 0
    for out in outs:
        try:
            nbytes, dt = generate(client, args.model, prompt, refs, aspect, out)
            print(f"{out}  ({nbytes / 1e6:.2f} MB, {dt:.0f} s)")
        except Exception as exc:  # noqa: BLE001
            print(f"{out}  FAILED: {exc}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
