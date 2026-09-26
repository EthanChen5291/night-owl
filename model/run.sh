#!/usr/bin/env bash
# Barn Owl model pipeline: features -> train -> backtest -> score. Runs on the parquet bake in
# $BARNOWL_PARQUET (default ~/divMap/data/parquet). Everything lands in model/out/.
set -euo pipefail
cd "$(dirname "$0")"
PY="uv run --with duckdb --with lightgbm --with h3 --with shap --with scikit-learn --with pandas --with pyarrow --with numpy --with matplotlib python"
export PYTHONWARNINGS=ignore
T0=$(date +%s)
step() { local t=$(date +%s); echo "== $1"; $PY "$1" "${@:2}"; echo "== $1 done in $(( $(date +%s) - t ))s"; }
step features.py "$@"
step train.py
step backtest.py
step score.py
echo "== pipeline done in $(( $(date +%s) - T0 ))s"
