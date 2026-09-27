# V5 live plush-to-map observation

On September 27, 2026, the locked V5 ONNX candidate observed the plush in the
existing Pi camera stream. The worker ran for 89.859 seconds with the locked
confidence 0.70, IoU 0.45, three hits in one second, two-second cooldown,
and person/width rules. It received 1,346 frames and inferred on all 1,346
(14.98 processed fps), with one backlog drop, no stale frames, and mean
inference time 59.15 ms. The camera service was already running; this check
did not restart it or control the camera.

The worker saved six local event crops between **04:52:03.340 and
04:52:14.210 UTC**. Root reviewed all six crops against the live camera view:
each shows the same visible plush near the center-lower part of the frame.
These are repeat alerts during one observed plush exposure, not six
independent detections or a recall measurement. The worker sent no events
to the API itself.

Only the first event, from node `live-v5-observer` at
`2026-09-27T04:52:03.340Z` (confidence 0.799), was copied unchanged to an
isolated relay directory. Its JSON SHA256 is
`e16e83522a2f0e3e4bcffd28bc52d91b5fcbbe86201ccb8de754348af5a13bd2`.
After a dry run, the relay made one POST through a Pi-loopback SSH forward to
the local rehearsal API. The API returned HTTP 200 with `accepted: true` on
attempt 1. A second relay scan found the recorded receipt and made no new
attempt. The other five events were never posted.

| Local rehearsal state for demo H3 `892a100d467ffff` | Before | After |
|---|---:|---:|
| API event count | 1 | 2 |
| Accepted sightings in cell posterior | 1 | 2 |
| Cell score B | 0.1297 | 0.1618 |
| Plan rank | 2 | 1 |
| Expected gain | 0.12344 | 0.14700 |

The pre-existing event-store SHA256 changed from
`c56d498b292e5f25e60e5051b99d4ccad3a8b95f8f780257c637b800ae66bc8a`
to `726fbae0f5bd3f327d37a5cf605730ad7bce0cf7de26732537b33b74810aa890`.
The frontend showed the new crop and two sightings at rank 1; root saved its
screenshot with the run evidence. The demo H3 was selected for the map
integration and is not a physical location claim for the indoor camera.

The bounded worker exited, removed its Unix socket, and the loopback reverse
forward was canceled. No worker, socket, or port 18000 remained afterward.
The [live evidence archive](artifacts/rat-litroom-v5-live-integration-evidence-20260927.zip)
contains six crop/JSON pairs, worker configuration and statistics, the single
relay journal, API before/after snapshots, source hashes, and the UI screenshot.

This confirms one coordinated **plush-to-local-map** path. It does not change
the failed [formal event test](V5_FORMAL_EVENT_RESULTS.md): that separate
recording produced 17 false alerts in its negative clip and missed one of
19 source-reviewed plush appearances. V5 remains a development candidate;
live rat, infrared, geographic field performance, and independent push recall
were not established by this check.
