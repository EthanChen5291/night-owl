#!/usr/bin/env python3
"""pir_test.py: watch the HC-SR501 PIR on a GPIO pin and print every transition.

Backends, tried in order: gpiozero (ships with Raspberry Pi OS), lgpio (gpiozero's
Pi 5 backend, usable directly), then the deprecated sysfs interface as a last resort.
Stdlib only apart from whichever GPIO library is found.

    python3 pir_test.py                 # GPIO4, run until Ctrl-C
    python3 pir_test.py --seconds 30    # stop after 30 s
    python3 pir_test.py --pin 17

Wiring (HC-SR501): VCC -> 5V, GND -> GND, OUT -> GPIO4 (header pin 7). OUT is 3.3 V.
The module needs ~60 s to settle after power-up; ignore triggers in that window.
"""

import argparse
import datetime as _dt
import os
import sys
import time


# --------------------------------------------------------------------------- backends

class _Gpiozero:
    name = "gpiozero"

    def __init__(self, pin):
        from gpiozero import DigitalInputDevice  # noqa: WPS433 (import inside on purpose)
        # HC-SR501 drives the line itself, so no pull. pull_up=False adds a pull-down,
        # which is harmless and keeps the pin from floating if the module is unplugged.
        self._dev = DigitalInputDevice(pin, pull_up=False)

    def read(self):
        return bool(self._dev.value)

    def close(self):
        self._dev.close()


class _Lgpio:
    name = "lgpio"

    def __init__(self, pin):
        import lgpio  # noqa: WPS433
        self._lg = lgpio
        self._pin = pin
        self._h = None
        last = None
        # Pi 5: header GPIOs are on gpiochip4 on older kernels and gpiochip0 on 6.12+.
        for chip in (0, 4):
            try:
                h = lgpio.gpiochip_open(chip)
                lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_DOWN)
                self._h = h
                self.name = f"lgpio (gpiochip{chip})"
                break
            except Exception as exc:  # noqa: BLE001
                last = exc
        if self._h is None:
            raise RuntimeError(f"lgpio: could not claim GPIO{pin} on gpiochip0/4: {last}")

    def read(self):
        return bool(self._lg.gpio_read(self._h, self._pin))

    def close(self):
        try:
            self._lg.gpio_free(self._h, self._pin)
            self._lg.gpiochip_close(self._h)
        except Exception:  # noqa: BLE001
            pass


class _Sysfs:
    """Deprecated /sys/class/gpio. Gone on recent Pi kernels; kept so the script degrades loudly."""

    name = "sysfs"

    def __init__(self, pin):
        base = "/sys/class/gpio"
        if not os.path.isdir(base):
            raise RuntimeError("sysfs GPIO not present on this kernel")
        # Pi 5 sysfs numbers are offset by the chip base; try the raw number then base+pin.
        self._path = None
        for num in self._candidates(pin):
            gdir = f"{base}/gpio{num}"
            try:
                if not os.path.isdir(gdir):
                    with open(f"{base}/export", "w") as f:
                        f.write(str(num))
                    time.sleep(0.1)
                with open(f"{gdir}/direction", "w") as f:
                    f.write("in")
                self._path = f"{gdir}/value"
                self._num = num
                break
            except OSError:
                continue
        if self._path is None:
            raise RuntimeError(f"sysfs: could not export GPIO{pin}")

    @staticmethod
    def _candidates(pin):
        yield pin
        try:
            for chip in sorted(os.listdir("/sys/class/gpio")):
                if chip.startswith("gpiochip"):
                    with open(f"/sys/class/gpio/{chip}/base") as f:
                        yield int(f.read().strip()) + pin
        except OSError:
            return

    def read(self):
        with open(self._path) as f:
            return f.read().strip() == "1"

    def close(self):
        try:
            with open("/sys/class/gpio/unexport", "w") as f:
                f.write(str(self._num))
        except OSError:
            pass


def open_pir(pin):
    """Return a reader object with .name, .read() -> bool, .close()."""
    errors = []
    for cls in (_Gpiozero, _Lgpio, _Sysfs):
        try:
            return cls(pin)
        except ImportError as exc:
            errors.append(f"{cls.name}: not installed ({exc})")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{cls.name}: {exc}")
    raise SystemExit("pir_test: no GPIO backend available:\n  " + "\n  ".join(errors))


# --------------------------------------------------------------------------- main

def _now():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Print HC-SR501 PIR transitions with timestamps.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--pin", type=int, default=4, help="BCM GPIO number the PIR OUT is on")
    ap.add_argument("--seconds", type=float, default=0, help="stop after this many seconds (0 = until Ctrl-C)")
    ap.add_argument("--hz", type=float, default=50, help="poll rate")
    args = ap.parse_args(argv)

    pir = open_pir(args.pin)
    state = pir.read()
    span = f"{args.seconds:g} s" if args.seconds else "until Ctrl-C"
    print(f"pir_test: {pir.name} backend, GPIO{args.pin}, {span}. Initial state: {'HIGH' if state else 'LOW'}",
          flush=True)

    rising = 0
    t_high = None
    t0 = time.monotonic()
    period = 1.0 / max(args.hz, 1.0)
    try:
        while True:
            now = pir.read()
            if now != state:
                if now:
                    rising += 1
                    t_high = time.monotonic()
                    print(f"{_now()}  HIGH  (motion)", flush=True)
                else:
                    held = f"  (held {time.monotonic() - t_high:.2f} s)" if t_high else ""
                    print(f"{_now()}  LOW {held}", flush=True)
                state = now
            if args.seconds and time.monotonic() - t0 >= args.seconds:
                break
            time.sleep(period)
    except KeyboardInterrupt:
        pass
    finally:
        pir.close()
    elapsed = time.monotonic() - t0
    print(f"pir_test: done, {rising} rising edges in {elapsed:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
