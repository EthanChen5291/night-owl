#!/usr/bin/env bash
# Download aarch64 wheels for the Pi's Python so the node can be set up with no internet.
#
#   ./bundle_wheels.sh 3.13        # Python version ON THE PI (python3 --version there), not on the Mac
#
# Produces wheels/ next to this script: pinned runtime packages, their dependencies, and a
# pip bootstrap wheel (manylinux_2_28 / 2_27 / 2014 aarch64, cp3X). Pi OS Trixie has glibc 2.41.
# Then on the Pi, inside a separate venv:
#
#   PIP_WHEEL=$(find wheels -maxdepth 1 -name 'pip-*.whl' -print -quit)
#   PYTHONPATH="$PIP_WHEEL" .venv/bin/python -m pip install --no-index --find-links wheels/ -r runtime-requirements.txt
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
  --index-url https://pypi.org/simple \
  --only-binary=:all: \
  --platform manylinux_2_28_aarch64 --platform manylinux_2_27_aarch64 \
  --platform manylinux2014_aarch64 \
  --python-version "$PYVER" --implementation cp \
  -d wheels/ \
  -r runtime-requirements.txt
python3 -m pip download \
  --index-url https://pypi.org/simple \
  --only-binary=:all: \
  --python-version "$PYVER" --implementation cp \
  -d wheels/ pip==26.1.2
(cd wheels && shasum -a 256 ./*.whl > SHA256SUMS)

echo
echo "wheels for cp${PYVER/./} aarch64 in $(pwd)/wheels:"
ls -1 wheels | sed 's/^/  /'
echo
echo "on the Pi:  use a separate venv and install runtime-requirements.txt from wheels/"
