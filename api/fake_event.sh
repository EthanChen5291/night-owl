#!/usr/bin/env bash
# Stage fallback (plan §9): post the canned demo event when the node or the network is dead.
#   ./api/fake_event.sh                 -> POST to http://localhost:8000/event
#   API=http://192.168.7.1:8000 ./api/fake_event.sh
set -euo pipefail
API="${API:-http://localhost:8000}"
HERE="$(cd "$(dirname "$0")" && pwd)"
TS="$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"
# stamp the current time so the feed shows "just now"
BODY="$(sed "s/\"ts\": *\"[^\"]*\"/\"ts\":\"$TS\"/" "$HERE/fixtures/event.demo.json")"
curl -s -X POST "$API/event" -H 'content-type: application/json' -d "$BODY"
echo
