#!/usr/bin/env python3
"""Node self-test: system, camera, stream, PIR, detector. PASS/FAIL per section, non-zero exit on any FAIL.

Run this first after ``scp -r pi/`` and the wheel install; it is the hour-6 gate checklist in one
command. Sections::

    system    python version (must match the wheels, 3.13 as bundled), arch (aarch64), free RAM
    camera    rpicam-still --list-cameras shows the IMX219 (needs dtoverlay=imx219,cam0)
    stream    10 frames through camera.py (rpicam-vid yuv420), reports fps and mean luminance
    pir       GPIO4 read for 3 s via gpiozero; reports high/low counts (wave a hand for a high)
    detector  load the ONNX model, run one zeros frame, time it (rat.onnx, else the World fallback)

``--skip pir,camera`` skips sections (e.g. on a Mac with ``--mock DIR`` for stream/detector).

Example::

    python3 selftest.py                      # on the Pi
    python3 selftest.py --mock ../frames --skip system,camera,pir   # on the Mac
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

SECTIONS = ["system", "camera", "stream", "pir", "detector"]
PIR_PIN = 4


def free_ram_mb() -> float | None:
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=3).stdout  # macOS
        free = sum(int(l.split(":")[1].strip().rstrip(".")) for l in out.splitlines()
                   if l.startswith(("Pages free", "Pages inactive")))
        return free * 4096 / 1e6
    except Exception:  # noqa: BLE001
        return None


def t_system(args):
    v = sys.version_info
    arch = platform.machine()
    ram = free_ram_mb()
    notes = [f"python {v.major}.{v.minor}.{v.micro}", f"arch {arch}", f"free RAM {ram:.0f} MB" if ram else "free RAM ?"]
    ok = True
    wheels = Path(__file__).resolve().parent / "wheels"
    if wheels.is_dir():
        tags = {p.name.split("-")[2] for p in wheels.glob("*.whl") if p.name.count("-") >= 4}
        mine = f"cp{v.major}{v.minor}"
        if tags and mine not in tags and "py3" not in tags:
            ok = False
            notes.append(f"wheels are for {sorted(tags)}, interpreter is {mine}: run bundle_wheels.sh {v.major}.{v.minor}")
    if ram is not None and ram < 300:
        ok = False
        notes.append("less than 300 MB free")
    return ok, "; ".join(notes)


def t_camera(args):
    if not shutil.which("rpicam-still"):
        return False, "rpicam-still not on PATH (not a Pi, or libcamera-apps missing)"
    try:
        r = subprocess.run(["rpicam-still", "--list-cameras"], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return False, "rpicam-still --list-cameras timed out"
    out = (r.stdout + r.stderr).strip()
    if "imx219" in out.lower():
        return True, "imx219 listed"
    if "no cameras" in out.lower() or not out:
        return False, "no cameras: check dtoverlay=imx219,cam0 in /boot/firmware/config.txt and the CAM0 ribbon"
    return True, out.splitlines()[0][:80]


def t_stream(args):
    try:
        from camera import frames
    except ImportError as e:
        return False, f"camera.py import: {e}"
    try:
        import numpy  # noqa: F401
    except ImportError:
        return False, "numpy missing"
    n, t0, means = 0, time.monotonic(), []
    try:
        for fr in frames(mock=args.mock, pace=False):
            means.append(float(fr.gray.mean()))
            n += 1
            if n >= 10:
                break
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    dt = time.monotonic() - t0
    if n < 10:
        return False, f"only {n} frames (rpicam-vid exited?)"
    return True, f"10 frames in {dt:.2f}s = {10 / dt:.1f} fps, mean Y {sum(means) / len(means):.0f}"


def t_pir(args):
    try:
        from gpiozero import DigitalInputDevice
    except ImportError:
        return False, "gpiozero not importable (apt install python3-gpiozero python3-lgpio)"
    try:
        pir = DigitalInputDevice(PIR_PIN, pull_up=False)
    except Exception as e:  # noqa: BLE001
        return False, f"GPIO{PIR_PIN}: {type(e).__name__}: {e}"
    hi = lo = 0
    t0 = time.monotonic()
    while time.monotonic() - t0 < 3.0:
        if pir.value:
            hi += 1
        else:
            lo += 1
        time.sleep(0.05)
    pir.close()
    return True, f"GPIO{PIR_PIN} over 3 s: high {hi}, low {lo}" + ("  (never high: wave a hand, check VCC/OUT)" if hi == 0 else "")


def t_detector(args):
    try:
        import numpy as np
        import detect as D
    except ImportError as e:
        return False, f"import: {e}"
    here = Path(__file__).resolve().parent
    cands = [Path(args.model)] if args.model else [here / D.MODEL, here / D.FALLBACK_MODEL]
    model = next((p for p in cands if p.is_file()), None)
    if model is None:
        return False, f"no model file ({', '.join(str(c) for c in cands)})"
    try:
        t0 = time.monotonic()
        det = D.Detector(str(model), gray=args.gray)
        t_load = time.monotonic() - t0
        frame = np.zeros((480, 640), dtype=np.uint8) if args.gray else np.zeros((480, 640, 3), dtype=np.uint8)
        det.infer(frame)  # warm-up
        t0 = time.monotonic()
        dets = det.infer(frame)
        t_inf = time.monotonic() - t0
    except Exception as e:  # noqa: BLE001
        return False, f"{model.name}: {type(e).__name__}: {e}"
    return True, f"{model.name} classes {det.names} imgsz {det.imgsz} load {t_load:.2f}s infer {t_inf * 1000:.0f} ms on zeros ({len(dets)} dets)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip", default="", help="comma-separated sections to skip: " + ",".join(SECTIONS))
    ap.add_argument("--only", default="", help="comma-separated sections to run")
    ap.add_argument("--mock", metavar="DIR", help="JPEG directory for the stream section (Mac)")
    ap.add_argument("--model", help="ONNX model for the detector section (default rat.onnx, else the World fallback)")
    ap.add_argument("--color", dest="gray", action="store_false", default=True, help="detector in colour mode")
    args = ap.parse_args(argv)

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    # resolve user paths before moving into the script's directory (models live next to it)
    args.mock = str(Path(args.mock).resolve()) if args.mock else None
    args.model = str(Path(args.model).resolve()) if args.model else None
    os.chdir(Path(__file__).resolve().parent)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    fails = 0
    for name in SECTIONS:
        if name in skip or (only and name not in only):
            print(f"{name:<9} SKIP")
            continue
        fn = globals()[f"t_{name}"]
        try:
            ok, note = fn(args)
        except Exception as e:  # noqa: BLE001
            ok, note = False, f"{type(e).__name__}: {e}"
        fails += 0 if ok else 1
        print(f"{name:<9} {'PASS' if ok else 'FAIL'}  {note}", flush=True)
    print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
