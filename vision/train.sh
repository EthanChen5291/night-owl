#!/usr/bin/env bash
# Train and validate a candidate. Promotion to pi/rat.onnx requires promote_model.py.
set -euo pipefail
cd "$(dirname "$0")"
python3 train_model.py "$@"
