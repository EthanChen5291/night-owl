# Optional live detector handoff

The Pi's existing `/home/pi/barn-owl/agent.py` owns its MJPEG camera. It has no local
frame listener. Its `Camera._read` callback currently sends frames to the recorder
and dashboard streamer. `agent_live.patch` adds a third callback only when
`OWL_DETECT_SOCKET` is set. With that variable absent, the bridge is off.

`live_bridge.py` runs under the agent's system Python and uses only the standard
library. Its camera callback puts the newest JPEG in a one-frame queue without
waiting for inference. A sender thread writes Unix datagrams to `live_worker.py`,
which runs under the isolated detector venv. If the worker is absent, slow, or
restarts, the camera callback keeps returning. The worker drains queued datagrams
to the newest frame, rejects frames over one second old, and resets the three-hit
gate whenever frame sequence numbers skip. It saves event JSON and a cropped JPEG
locally. It does not post to the API, use GPIO, or start a camera.

At 15 camera frames per second, three consecutive processed hits need enough CPU
headroom to avoid dropped frames. The V4 saved-frame median was about 56 ms per
inference, but that does not establish live throughput. `run_stats.json` records
received and inferred fps, backlog drops, sequence gaps, frame age, inference
time, and person suppression during a live trial.

## Review and offline check

The patch was made against Pi agent SHA256
`756d75843c4eff2a83fad1c563848a646f584b7df2fe2130c4c6db31f8eb7e78`.
It changes only callback setup and shutdown. Before applying it anywhere, check
the target file's hash and stop if it differs. The current V4 ONNX SHA256 is
`fb557bd9c1dafa7466a45afb50ac47668550a666a44f1791af714011a0bf1b27`.
Read-only Pi inspection on 2026-09-27 confirmed the active unit is
`barn-owl.service` (`/etc/systemd/system/barn-owl.service`), with
`ExecStart=/usr/bin/python3 -u /home/pi/barn-owl/agent.py`, environment file
`/etc/barn-owl.env`, and no drop-ins at that time. Recheck those facts before
changing the service.

Run the local tests without touching the Pi:

```sh
vision/.venv/bin/python -m unittest vision.tests.test_live_handoff -v
```

For a saved-frame dry run on the Pi after copying `live_bridge.py` and
`live_worker.py` into the V4 candidate slot, run the worker in one shell:

```sh
scp vision/pi/{live_bridge.py,live_worker.py} barn-owl-pi:/home/pi/barn-owl-candidates/v4-fb557bd9/
```

Then, on the Pi:

```sh
cd ~/barn-owl-candidates/v4-fb557bd9
../v3-3214f2a0/.venv/bin/python live_worker.py \
  --socket "$HOME/barn-owl-candidates/live-frames.sock" \
  --model "$PWD/rat.onnx" \
  --expected-sha256 fb557bd9c1dafa7466a45afb50ac47668550a666a44f1791af714011a0bf1b27 \
  --conf 0.70 --iou 0.45 --floor-y 0 --hits 3 --window 1 --cooldown 2 \
  --events-dir "$PWD/saved-frame-trial-1" --max-frames 3
```

In another shell, send three copies of the saved positive JPEG. This uses no
camera, GPIO, service, or API:

```sh
cd ~/barn-owl-candidates/v4-fb557bd9
python3 - <<'PY'
from pathlib import Path
import time
from live_bridge import FrameHandoff

bridge = FrameHandoff(str(Path.home() / 'barn-owl-candidates/live-frames.sock'))
jpeg = Path('positive.jpg').read_bytes()
for _ in range(3):
    bridge(jpeg)
    time.sleep(.1)
time.sleep(.2)
bridge.close()
PY
```

Inspect `saved-frame-trial-1/run_config.json`, `run_stats.json`, and the saved
event crop. Choose a new `--events-dir` for every worker run; the CLI refuses to
reuse an existing directory.

## Agent patch and rollback, after approval

Do not apply these steps during the offline check. The agent requires a restart
to load source changes, and enabling the callback requires a service environment
change. Stage `live_bridge.py` and `agent_live.patch` next to the existing Pi
agent after approval:

```sh
scp vision/pi/{live_bridge.py,agent_live.patch} barn-owl-pi:/home/pi/barn-owl/
```

Then run these commands on the Pi:

```sh
cd /home/pi/barn-owl
systemctl show barn-owl.service -p FragmentPath -p DropInPaths -p ExecStart -p EnvironmentFiles
echo '756d75843c4eff2a83fad1c563848a646f584b7df2fe2130c4c6db31f8eb7e78  agent.py' | sha256sum -c -
test ! -e agent.py.pre-live-756d7584
cp -p agent.py agent.py.pre-live-756d7584
patch --dry-run -p0 < agent_live.patch
patch -p0 < agent_live.patch
python3 -m py_compile agent.py live_bridge.py
```

At this point the callback remains off. To enable a reviewed trial, first start
the V4 worker with a new events directory, then add the environment variable to
the service and restart it:

```sh
sudo install -d /etc/systemd/system/barn-owl.service.d
sudo sh -c 'set -C; printf "[Service]\nEnvironment=OWL_DETECT_SOCKET=/home/pi/barn-owl-candidates/live-frames.sock\n" > /etc/systemd/system/barn-owl.service.d/detector-bridge.conf'
sudo systemctl daemon-reload
sudo systemctl restart barn-owl.service
```

The `set -C` redirection fails if that named drop-in already exists. Leave all
other drop-ins in place. If the source backup filename already exists, stop
before patching and choose a new unique backup name in both apply and rollback
commands.

The dashboard viewer or recording control still decides when the existing
camera runs. Watch `run_stats.json` after stopping the worker and inspect event
crops. A three-hit alert should be evaluated against actual push timestamps;
saved or sparse frames do not establish event recall.

To roll back, remove the service override, restore the exact backed-up agent,
reload and restart the service, then stop the worker. `live_worker.py` removes its
socket on clean exit:

```sh
sudo rm /etc/systemd/system/barn-owl.service.d/detector-bridge.conf
sudo systemctl daemon-reload
cd /home/pi/barn-owl
cp -p agent.py.pre-live-756d7584 agent.py
sudo systemctl restart barn-owl.service
```
