#!/usr/bin/env bash
# Start the Barn Owl API on 0.0.0.0:8000 (the Pi posts to http://192.168.7.1:8000, the web app reads from it).
set -euo pipefail
cd "$(dirname "$0")"
exec uv run uvicorn main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" "$@"
