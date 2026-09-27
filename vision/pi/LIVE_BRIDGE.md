# NightOwl live frame handoff

The Pi's existing `/home/pi/barn-owl/agent.py` owns the camera. The reviewed `agent_live.patch` adds a JPEG callback guarded by `OWL_DETECT_SOCKET`. `live_bridge.py` keeps only the newest frame and sends it over a Unix datagram socket. A separate `live_worker.py` process runs ONNX inference, saves event JSON and crop JPEGs, and writes `run_stats.json`. The camera callback never waits for inference. The worker has no API or LED output; `event_relay.py` handles optional delivery in another process.

The observed V5 trial is documented in [V5 live results](../V5_LIVE_RESULTS.md). It processed 1,346 camera frames in 89.859 seconds at confidence 0.70, saved six crops from one visible plush exposure, and relayed one unchanged event to the local API. The API accepted it and the map updated. The worker, socket, and relay stopped after the trial. As observed then, the camera service kept the bridge drop-in enabled; without a worker socket, the callback drops frames without blocking the agent. This is a historical end state, so inspect the Pi before another session. V5's separate [formal event test](../V5_FORMAL_EVENT_RESULTS.md) failed.

## Local checks

Run the code tests without a camera or API connection:

```sh
vision/.venv/bin/python -m unittest vision.tests.test_live_handoff -v
python3 -m unittest vision.tests.test_event_relay -v
api/.venv/bin/python -m unittest vision.tests.test_event_relay_api -v
```

The existing V5 Pi model was staged at `/home/pi/barn-owl-candidates/v5-652a05e8/rat.onnx`, SHA256 `652a05e8c08aaee11a2b4d3c9ae4c737387bf8ffcac3372a4d83d0df7d80ed3d`. Its isolated ONNX Runtime venv came from the earlier `v3-3214f2a0` slot. Before using any slot, verify its model hash, worker source, and running service state. Do not infer a current deployment from the saved trial report.

## Local-only worker observation

The agent's dashboard viewer or recorder controls when camera JPEGs flow. A worker can observe those JPEGs without opening the camera itself. On the Pi, after checking that the reviewed bridge is installed, run the worker from the V5 slot with a **new, absent** events directory:

```sh
cd ~/barn-owl-candidates/v5-652a05e8
../v3-3214f2a0/.venv/bin/python live_worker.py \
  --socket "$HOME/barn-owl-candidates/live-frames.sock" \
  --model "$PWD/rat.onnx" \
  --expected-sha256 652a05e8c08aaee11a2b4d3c9ae4c737387bf8ffcac3372a4d83d0df7d80ed3d \
  --conf 0.70 --iou 0.45 --floor-y 0 \
  --person-iou 0.3 --person-contain 0.7 \
  --min-rat-width 0.01 --max-rat-width 0.65 \
  --hits 3 --window 1 --cooldown 2 \
  --events-dir "$PWD/live-observation-NEW-NAME"
```

Press Ctrl-C to stop the worker. It writes `run_stats.json` and removes its socket on clean exit; the camera service stays up. Inspect processed and received frame counts, backlog drops, stale frames, sequence gaps, inference time, and every crop. The three-hit gate resets across dropped sequences, so a saved-frame inference time alone cannot establish live event recall. The V5 trial measured 59.15 ms mean inference and one backlog drop. A worker run started before the viewer opens includes idle time in its fps statistics.

## Optional event relay

`event_relay.py` reads complete `event_*.json` files from one worker events directory. It ignores worker config and stats. Dry-run inspection sends nothing:

```sh
cd ~/barn-owl-candidates/v5-652a05e8
python3 event_relay.py --events-dir "$PWD/live-observation-NEW-NAME" --once
```

To send reviewed events, start it separately with both `--post` and the direct API URL:

```sh
python3 event_relay.py --events-dir "$PWD/live-observation-NEW-NAME" \
  --post --api 'http://<reviewed-api-host>:8000'
```

The relay writes `relay_receipts.jsonl` with durable attempt and server-receipt records. Its default budget is three attempts per event, including restarts. A completed receipt prevents another delivery from that directory. `accepted:false` means the API handled the event without adding a sighting; inspect the API response and stored posterior. Redirects are rejected. The journal binds receipts to the API destination, so reusing the directory with a different URL fails before POST. The API's body-based deduplication protects the posterior if a request succeeded but its response was lost, provided the API kept its event store.

The V5 trial relayed only the first of six events, once, through a temporary Pi-loopback forward. That forward was canceled. Do not assume a route to the local API is still open.

## Agent patch and rollback record

The reviewed patch was built against agent SHA256 `756d75843c4eff2a83fad1c563848a646f584b7df2fe2130c4c6db31f8eb7e78`. The observed unit was `barn-owl.service`, with `ExecStart=/usr/bin/python3 -u /home/pi/barn-owl/agent.py` and environment file `/etc/nightowl.env`. The bridge override was `/etc/systemd/system/barn-owl.service.d/detector-bridge.conf`, setting `OWL_DETECT_SOCKET=/home/pi/barn-owl-candidates/live-frames.sock`. The original agent backup used the unique name `agent.py.pre-live-756d7584`.

These names describe the reviewed Pi at the time of the V5 trial. Before any source or service change, read the active unit, drop-ins, agent hash, and backup contents. Do not reapply `agent_live.patch` to an agent that already contains it, overwrite the backup, or remove an unrelated drop-in. A rollback needs a separate reviewed service restart: stop the worker, restore the matching backup, remove only the detector-bridge override, reload systemd, and restart `barn-owl.service`. The V5 live trial left the agent running and did not perform that rollback.

For a later approved rollback, use this sequence only after the read-only
checks show the same backup and detector-specific drop-in. It leaves other
service overrides in place:

```sh
systemctl show barn-owl.service -p FragmentPath -p DropInPaths -p ExecStart -p EnvironmentFiles
cd /home/pi/barn-owl
sha256sum agent.py agent.py.pre-live-756d7584
cat /etc/systemd/system/barn-owl.service.d/detector-bridge.conf
# Stop the detector worker in its own shell before continuing.
test -f agent.py.pre-live-756d7584
sudo rm /etc/systemd/system/barn-owl.service.d/detector-bridge.conf
cp -p agent.py.pre-live-756d7584 agent.py
sudo systemctl daemon-reload
sudo systemctl restart barn-owl.service
systemctl is-active barn-owl.service
```
