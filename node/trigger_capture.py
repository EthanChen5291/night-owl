#!/usr/bin/env python3
"""trigger_capture.py: wait for a PIR rising edge, then take an IR-friendly still with rpicam-still.

    python3 trigger_capture.py                    # GPIO4, capture forever into captures/
    python3 trigger_capture.py --count 3          # three captures then exit
    python3 trigger_capture.py --small            # 640x480 instead of 1640x1232
    python3 trigger_capture.py --dry-run          # print the rpicam-still command, do not run it

--dry-run works on a Mac with no GPIO library: it prints the command once and exits.
On the Pi, --dry-run still waits for PIR edges and prints instead of capturing.

Defaults are tuned for the NoIR + 850 nm board at rail distance: gain 8, 30 ms shutter,
greyworld AWB (tames the magenta cast), no preview, 1 s settle. Only one rpicam-* process
can own the camera; stop camera.py / rpicam-vid before running this.
"""

import argparse
import datetime as _dt
import os
import shlex
import subprocess
import sys
import time

# Optional GPIO backends. Imported inside try so the script loads on any machine.
try:
    from gpiozero import DigitalInputDevice as _DigitalInputDevice
except Exception:  # noqa: BLE001  (ImportError, or gpiozero present but no pin factory)
    _DigitalInputDevice = None
try:
    import lgpio as _lgpio
except Exception:  # noqa: BLE001
    _lgpio = None


class Pir:
    """Minimal PIR reader: gpiozero, else lgpio. Raises RuntimeError if neither works."""

    def __init__(self, pin):
        self.name = None
        self._dev = None
        self._h = None
        self._pin = pin
        if _DigitalInputDevice is not None:
            try:
                self._dev = _DigitalInputDevice(pin, pull_up=False)
                self.name = "gpiozero"
                return
            except Exception as exc:  # noqa: BLE001
                err = f"gpiozero: {exc}"
        else:
            err = "gpiozero: not installed"
        if _lgpio is not None:
            for chip in (0, 4):
                try:
                    h = _lgpio.gpiochip_open(chip)
                    _lgpio.gpio_claim_input(h, pin, _lgpio.SET_PULL_DOWN)
                    self._h = h
                    self.name = f"lgpio (gpiochip{chip})"
                    return
                except Exception as exc:  # noqa: BLE001
                    err += f"; lgpio chip{chip}: {exc}"
        else:
            err += "; lgpio: not installed"
        raise RuntimeError(err)

    def read(self):
        if self._dev is not None:
            return bool(self._dev.value)
        return bool(_lgpio.gpio_read(self._h, self._pin))

    def close(self):
        try:
            if self._dev is not None:
                self._dev.close()
            elif self._h is not None:
                _lgpio.gpio_free(self._h, self._pin)
                _lgpio.gpiochip_close(self._h)
        except Exception:  # noqa: BLE001
            pass


def build_cmd(args, out_path):
    """The rpicam-still invocation for one capture."""
    cmd = [
        "rpicam-still",
        "--nopreview",
        "-t", str(args.timeout),
        "--gain", str(args.gain),
        "--shutter", str(args.shutter),
        "--awb", args.awb,
        "--width", str(args.width),
        "--height", str(args.height),
        "-q", str(args.quality),
        "-o", out_path,
    ]
    if args.immediate:
        cmd.insert(2, "--immediate")
    if args.extra:
        cmd.extend(shlex.split(args.extra))
    return cmd


def stamp():
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def capture(args, out_path):
    cmd = build_cmd(args, out_path)
    if args.dry_run:
        print("  " + shlex.join(cmd), flush=True)
        return True
    t0 = time.monotonic()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout / 1000 + 20)
    except FileNotFoundError:
        print("trigger_capture: rpicam-still not found (this is not a Pi, or rpicam-apps is missing)",
              file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print("trigger_capture: rpicam-still hung; is another rpicam process holding the camera?",
              file=sys.stderr)
        return False
    dt = time.monotonic() - t0
    if res.returncode != 0 or not os.path.exists(out_path):
        tail = (res.stderr or "").strip().splitlines()[-3:]
        print(f"trigger_capture: rpicam-still failed (rc={res.returncode}): {' | '.join(tail)}",
              file=sys.stderr)
        return False
    size = os.path.getsize(out_path) / 1e6
    return f"{out_path} ({size:.2f} MB, {dt:.1f} s)"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="PIR-triggered IR stills with rpicam-still.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--pin", type=int, default=4, help="BCM GPIO of the PIR OUT")
    ap.add_argument("--count", type=int, default=0, help="captures before exiting (0 = forever)")
    ap.add_argument("--outdir", default="captures", help="where the JPEGs go (<outdir>/<YYYYMMDD-HHMMSS>.jpg)")
    ap.add_argument("--debounce", type=float, default=2.0, help="seconds to ignore new edges after a capture")
    ap.add_argument("--gain", type=float, default=8, help="analogue gain")
    ap.add_argument("--shutter", type=int, default=30000, help="shutter, microseconds")
    ap.add_argument("--awb", default="greyworld", help="AWB mode (greyworld suits NoIR under IR)")
    ap.add_argument("--width", type=int, default=1640)
    ap.add_argument("--height", type=int, default=1232)
    ap.add_argument("--small", action="store_true", help="shortcut for --width 640 --height 480")
    ap.add_argument("--quality", type=int, default=90, help="JPEG quality")
    ap.add_argument("--timeout", type=int, default=1000, help="rpicam -t settle time, ms")
    ap.add_argument("--immediate", action="store_true", help="pass --immediate (skip AE/AWB settle)")
    ap.add_argument("--extra", default="", help="extra rpicam-still args, quoted, appended verbatim")
    ap.add_argument("--dry-run", action="store_true", help="print the command instead of running it")
    args = ap.parse_args(argv)

    if args.small:
        args.width, args.height = 640, 480

    try:
        pir = Pir(args.pin)
    except RuntimeError as exc:
        if args.dry_run:
            print(f"trigger_capture: no GPIO backend ({exc}); dry-run, printing the command once:")
            capture(args, os.path.join(args.outdir, f"{stamp()}.jpg"))
            return 0
        print(f"trigger_capture: no GPIO backend: {exc}", file=sys.stderr)
        return 2

    if not args.dry_run:
        os.makedirs(args.outdir, exist_ok=True)

    print(f"trigger_capture: {pir.name} backend, GPIO{args.pin}, count={args.count or 'inf'}, "
          f"debounce={args.debounce:g} s, outdir={args.outdir}{' (dry-run)' if args.dry_run else ''}",
          flush=True)
    print("waiting for PIR...", flush=True)

    taken = 0
    failed = 0
    last = pir.read()
    ready_at = 0.0
    try:
        while not args.count or taken < args.count:
            now = pir.read()
            edge = now and not last
            last = now
            if edge and time.monotonic() >= ready_at:
                out_path = os.path.join(args.outdir, f"{stamp()}.jpg")
                n = taken + 1
                label = f"{n}/{args.count}" if args.count else str(n)
                print(f"{_dt.datetime.now():%Y-%m-%d %H:%M:%S}  edge {label} -> ", end="", flush=True)
                result = capture(args, out_path)
                if result:
                    print(result if isinstance(result, str) else "", flush=True)
                    taken += 1
                    failed = 0
                else:
                    failed += 1
                    if failed >= 3:
                        print("trigger_capture: three failures in a row, giving up", file=sys.stderr)
                        return 1
                ready_at = time.monotonic() + args.debounce
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        pir.close()
    print(f"trigger_capture: done, {taken} captures", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
