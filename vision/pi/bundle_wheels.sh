#!/usr/bin/env bash
# Download aarch64 wheels for the Pi's Python so the node can be set up with no internet.
#
#   ./bundle_wheels.sh 3.13        # Python version ON THE PI (python3 --version there), not on the Mac
#
# Produces wheels/ next to this script: onnxruntime, numpy, opencv-python-headless and their
# dependencies (manylinux_2_17 / manylinux2014 aarch64, cp3X). Then on the Pi:
#
#   pip install --no-index --find-links wheels/ onnxruntime numpy opencv-python-headless
#
# (use `python3 -m pip ... --break-system-packages` on Trixie if you are not in a venv; a venv is
# cleaner: `python3 -m venv --system-site-packages ~/venv && . ~/venv/bin/activate`, the
# --system-site-packages keeps apt's gpiozero visible).
#
# The version must match exactly: a cp313 wheel does not install on 3.12. That is the hour-6 risk
# in the README; run this again with the right version if selftest.py's system section fails.
set -euo pipefail
cd "$(dirname "$0")"

PYVER="${1:-3.13}"
case "$PYVER" in
  3.*) ;;
  *) echo "usage: $0 <pyver like 3.13>" >&2; exit 2 ;;
esac

mkdir -p wheels
python3 -m pip download \
  --only-binary=:all: \
  --platform manylinux_2_17_aarch64 --platform manylinux2014_aarch64 \
  --python-version "$PYVER" --implementation cp \
  -d wheels/ \
  onnxruntime numpy opencv-python-headless

echo
echo "wheels for cp${PYVER/./} aarch64 in $(pwd)/wheels:"
ls -1 wheels | sed 's/^/  /'
echo
echo "on the Pi:  pip install --no-index --find-links wheels/ onnxruntime numpy opencv-python-headless"
