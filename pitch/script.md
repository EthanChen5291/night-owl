# Barn Owl: three-minute pitch

Use the live map on slide 2 and the verified live Pi event screenshot on slide 4. The spoken text is about 335 words; leave time to show the map.

## 1. Reporting gap, 0:00–0:25

311 tells us where people report rats, not where all rats are. Barn Owl adds a second signal: active rat signs found during city inspections of swept blocks.

## 2. Two signals, 0:25–1:00

We score each block-sized cell two ways. Model A estimates complaints. Model B estimates active-sign risk from physical and environmental features, without complaint counts. Their percentile gap is our Silence Score. In the current export, East Harlem North has zero complaints in the prior year but ranks tenth of 5,170 cells on silence. A West Village cell has 31 complaints and lower modeled risk. [Toggle complaints, risk, silence on the map.] These are rankings, not rat counts.

## 3. Backtest, 1:00–1:40

We replayed 119 months, training on earlier data each time. Among cells the city swept, Model B's top 50 averaged 19.5 percent of inspected lots with active signs. Ranking by prior 311 calls averaged 15.2 percent. That 4.3-point gap applies only to swept cells; we do not know what inspectors would have found elsewhere.

## 4. Live Pi event, 1:40–2:30

The planner proposes tree-pit sites with high risk and a large data gap. Our physical Pi camera then watched a room-lit plush for 90 seconds. It processed 1,346 frames and saved six crops, all showing the plush. We relayed one genuine event to the local API. The map moved that site from rank two to one, and its served score from 13.0 to 16.2 percent. [Show the live event screenshot.] This is a real end-to-end prototype loop. The event updates a chosen prior; it does not retrain the city model.

## 5. What is real, 2:30–3:00

The detector still needs work. A fixed recorded test alerted on 18 of 19 reviewed plush appearances, but fired 17 false alerts on a cap and shoe over 190 seconds. That fails our event gate. A separate fresh box test also did not establish our .90 target; its as-run score has known label defects. This is a room-lit plush prototype. We will improve distractor handling and test on new footage before any pilot.

## Presenter guardrails

- The 19.5 and 15.2 percent bars are mean monthly, lot-weighted active-sign shares **within the top 50 swept cells**. They compare rankings on an observed sample, not citywide prevalence or a causal deployment effect. The Model B bar is a **risk ranking**, not a Silence Score ranking.
- The East Harlem North and West Village values are examples of model output for two cells. They do not measure prevalence or prove an income effect. The screenshots' income and inspection denominators were not reproducible from the available exports, so the deck omits them.
- The V4 same-session reserve scored rat AP50 .925806 on 59 frames. A separate locked new-room test scored .882675 on 439 reviewed frames, below the .90 box target. Its full recorded-video replay produced nine plush events and one false dark-case alert in the moving clip, zero events during one parked-plush exposure, and zero events over 181.21 seconds of a people-only clip. The parked miss motivated V5 adaptation.
- V5 uses prior new-room clips as **development** data. Its selected epoch-35 checkpoint scored rat AP50 .960806 on its weakest selected development clip and .975279 over the 146-frame combined development set. These are tuned validation results, not 97.5% accuracy or event recall. The locked V5 model measured **.615779 rat AP50 on 369 fresh frames as run**, including .703102 on the 193-frame positive clip; combined person AP50 was .492688. PyTorch and ONNX AP scores agreed exactly. Completed source-only review of all 193 positive sampled frames found shifted and oversized reference boxes. Thirty-one correction proposals are drafts; none was adopted or rescored. Frozen labels and predictions remain unchanged, so .615779 is the as-run score with known annotation defects, not a corrected performance estimate. The test did **not** establish the .90 rat-box target. This one held-out source test cannot establish performance across other cameras or field sites.
- At fixed runtime confidence .70, recorded V5 development replay fired 14 plush events in the moving new-room clip, 64 during one parked exposure, 64 on old metal footage, and 44 on old floor footage. It fired zero events on 181.21 seconds of people-only footage. The earlier fresh replay emitted 34 events in the positive clip; an independent reviewer confirmed every saved crop targeted the visible plush. It emitted zero events in a 175.937-second negative clip. These are repeated firings, not independent encounters or timed push recall. That earlier fresh source had only two complete coarse positive presences and a negative reel under three minutes, so it alone could not satisfy the 20-push / three-minute-negative gate. The second presence first alerted after a 58.890-second delay near the image edge.
- In a separate **live Pi camera** observation, V5 processed 1,346 frames in 89.859 seconds (14.98 processed frames/s; 59.15 ms mean inference). Six saved event crops all showed the plush on visual review. Exactly one genuine event was relayed to the local API and accepted (HTTP 200), at `2026-09-27T04:52:03.340Z` from `live-v5-observer` for H3 `892a100d467ffff`. The API's served cell score changed .1297→.1618, sightings 1→2, and candidate rank 2→1. The other five saved events were not posted. This proves one physical Pi-to-map loop, not reliability across scenes or nights. PIR wakes capture; it does not recognize rats.
- The **fixed formal recorded event test failed**: 18 of 19 reviewed plush appearances produced a verified alert (94.7% observed), but 17 false events occurred in 190.409 seconds without a plush (5.357/min versus a <0.5/min gate). All 43 positive event crops show the plush, including 25 repeat firings; 16 false events targeted one cap, and one targeted a shoe. The short first appearance was missed, and the test had 19 rather than 20 source appearances. All 60 emitted crops were independently audited. This test did not POST to the API.
- The earlier V2 saved-video integration replay produced exactly one accepted event from original `zoom15_b` footage at 59–63 seconds. It exercised exported ONNX, Pi Detector rules, crop, local API, and frontend map on a Mac. Score moved .0923→.1297 and candidate rank 11→2. This is historical recorded-footage integration evidence; slide 4 uses the newer V5 live Pi event.
- An accepted event updates a chosen Beta prior and may rerank candidate sites. It does not refit Model B. Model exports also contain historical sweep-informed posteriors; use the API's live event value when discussing the stage update.
- The prop footage is room-lit. IR capture does not establish model performance under IR; no wild-rat test or field deployment has occurred. The live Pi screenshot shows one accepted event, not a general event-gate pass.

## Source snapshot

`model/out/backtest.json` and `model/out/cells.json`, read 2026-09-27. The [frozen V5 fresh-test report](evidence/v5-fresh-test-provisional.json) preserves the as-run box scores; [V5 fresh results](../vision/V5_FRESH_RESULTS.md) records crop and source-label review. [V5 formal event results](../vision/V5_FORMAL_EVENT_RESULTS.md) records the failed fixed event gate and completed crop audit. The [live integration result](evidence/v5-live-integration-result.json), [live run stats](evidence/v5-live-run-stats.json), and [map screenshot](assets/live-pi-map-20260927.png) preserve the live prototype loop. The [V5 development candidate ZIP](../vision/artifacts/rat-litroom-v5-development-candidate-20260927.zip) contains tuned metrics and model lock. The [V4 new-room ZIP](../vision/artifacts/rat-litroom-v4-new-room-evaluation-20260927.zip) preserves the previous failure. The physical rig photo came from Sanjavan's team media.
