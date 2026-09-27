#!/usr/bin/env bash
# Start the NightOwl API on 0.0.0.0:8000 (the Pi posts to http://192.168.7.1:8000, the web app reads from it).
set -euo pipefail
cd "$(dirname "$0")"
# Load the repo-root .env (XAI_API_KEY and friends) so the assistant and dashboards are configured. Values already
# exported in the shell win: the file only fills variables that are unset. Lines are KEY=value, with optional
# "export", optional surrounding quotes, and # comments. Values are taken literally, never expanded.
load_env() {
  local line key value
  while IFS= read -r line || [[ -n $line ]]; do
    line=${line%$'\r'}
    [[ $line =~ ^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
    key=${BASH_REMATCH[2]}
    value=${BASH_REMATCH[3]}
    if [[ $value == \"*\" || $value == \'*\' ]]; then value=${value:1:${#value}-2}; fi
    [[ -n ${!key:-} ]] || export "$key=$value"
  done < "$1"
}
[[ -f ../.env ]] && load_env ../.env
exec uv run uvicorn main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" "$@"
