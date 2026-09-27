# Barn Owl: three-minute pitch

Use the live map on slide 2 and the verified recorded-footage replay on slide 4. Slide 4 shows the physical prototype photographed at the hackathon. The spoken text is about 335 words; leave time for the replay.

## 1. Reporting gap, 0:00–0:25

311 tells us where people report rats, not where all rats are. Barn Owl adds a second signal: active rat signs found during city inspections of swept blocks.

## 2. Two signals, 0:25–1:00

We score each block-sized cell two ways. Model A estimates complaints. Model B estimates active-sign risk from physical and environmental features, without complaint counts. Their percentile gap is our Silence Score. In the current export, East Harlem North has zero complaints in the prior year but ranks tenth of 5,170 cells on silence. A West Village cell has 31 complaints and lower modeled risk. [Toggle complaints, risk, silence on the map.] These are rankings, not rat counts.

## 3. Backtest, 1:00–1:40

We replayed 119 months, training on earlier data each time. Among cells the city swept, Model B's top 50 averaged 19.5 percent of inspected lots with active signs. Ranking by prior 311 calls averaged 15.2 percent. That 4.3-point gap applies only to swept cells; we do not know what inspectors would have found elsewhere.

## 4. Node and recorded trigger, 1:40–2:30

The planner proposes tree-pit sites with high risk and a large data gap. In an earlier replay using our V2 detector, one event from recorded room-lit footage reached the API and map. The score moved from 9.2 to 13.0 percent; a site rose from rank 11 to 2. [Show the replay. Name it as recorded footage.] This verifies that software loop for V2. The event updates a chosen prior; the city model does not retrain on stage.

## 5. What is real, 2:30–3:00

V4's new-room test missed our target at .883 rat AP50. We adapted the detector; V5 reached .961 on its weakest tuned clip. A fresh test still did not establish our .90 target. Source review found label errors, with no corrected score yet. This is a room-lit plush prototype. Positive live-camera integration and the formal push gate remain open. We will improve and retest before any pilot.

## Presenter guardrails

- The 19.5 and 15.2 percent bars are mean monthly, lot-weighted active-sign shares **within the top 50 swept cells**. They compare rankings on an observed sample, not citywide prevalence or a causal deployment effect. The Model B bar is a **risk ranking**, not a Silence Score ranking.
- The East Harlem North and West Village values are examples of model output for two cells. They do not measure prevalence or prove an income effect. The screenshots' income and inspection denominators were not reproducible from the available exports, so the deck omits them.
- The V4 same-session reserve scored rat AP50 .925806 on 59 frames. A separate locked new-room test scored .882675 on 439 reviewed frames, below the .90 box target. Its full recorded-video replay produced nine plush events and one false dark-case alert in the moving clip, zero events during one parked-plush exposure, and zero events over 181.21 seconds of a people-only clip. The parked miss motivated V5 adaptation.
- V5 uses prior new-room clips as **development** data. Its selected epoch-35 checkpoint scored rat AP50 .960806 on its weakest selected development clip and .975279 over the 146-frame combined development set. These are tuned validation results, not 97.5% accuracy or event recall. The locked V5 model measured **.615779 rat AP50 on 369 fresh frames as run**, including .703102 on the 193-frame positive clip; combined person AP50 was .492688. PyTorch and ONNX AP scores agreed exactly. Completed source-only review of all 193 positive sampled frames found shifted and oversized reference boxes. Thirty-one correction proposals are drafts; none was adopted or rescored. Frozen labels and predictions remain unchanged, so .615779 is the as-run score with known annotation defects, not a corrected performance estimate. The test did **not** establish the .90 rat-box target. This one held-out source test cannot establish performance across other cameras or field sites.
- At fixed runtime confidence .70, recorded V5 development replay fired 14 plush events in the moving new-room clip, 64 during one parked exposure, 64 on old metal footage, and 44 on old floor footage. It fired zero events on 181.21 seconds of people-only footage. The fresh replay emitted 34 events in the positive clip; an independent reviewer confirmed every saved crop targeted the visible plush. It emitted zero events in a 175.937-second negative clip. These are repeated firings, not independent encounters or timed push recall. The fresh source has only two complete coarse positive presences and a negative reel under three minutes, so it cannot pass the formal 20-push / three-minute-negative gate. The second presence first alerted after a 58.890-second delay near the image edge.
- V5 ONNX ran on a **saved positive frame** on the physical Pi: top rat confidence .931 and median inference 60.23 ms across 20 timed runs. A separate live-camera trial processed frames without a plush target. Positive plush detection from the live camera and live end-to-end map updates remain unverified. PIR wakes capture; it does not recognize rats.
- The earlier V2 saved-video integration replay produced exactly one accepted event from original `zoom15_b` footage at 59–63 seconds. Exported ONNX, Pi Detector rules, crop, local API, and frontend map were exercised on a Mac. Score moved 0.0923→0.1297 and candidate rank 11→2. This is recorded-footage integration evidence for V2; V5 has not been verified through that API path.
- An accepted event updates a chosen Beta prior and may rerank candidate sites. It does not refit Model B. Model exports also contain historical sweep-informed posteriors; use the API's live event value when discussing the stage update.
- The prop footage is room-lit. IR capture does not establish model performance under IR; no wild-rat test or field deployment has occurred. If the live feed fails or an event is canned, say which part ran.

## Source snapshot

`model/out/backtest.json` and `model/out/cells.json`, read 2026-09-27. The [frozen V5 fresh-test report](evidence/v5-fresh-test-provisional.json) preserves the as-run box scores and machine event counts; [V5 fresh results](../vision/V5_FRESH_RESULTS.md) records the completed event-crop and source-only label reviews, plus the unadopted correction proposals. The [V5 development candidate ZIP](../vision/artifacts/rat-litroom-v5-development-candidate-20260927.zip) contains `reports/metrics.json`, `reports/candidate_lock.json`, `reports/dev_replay/`, and `reports/pi_saved_frame_smoke.json`. The [V4 new-room ZIP](../vision/artifacts/rat-litroom-v4-new-room-evaluation-20260927.zip) preserves the failure and event audit. The physical rig photo came from Sanjavan's team media; the earlier V2 recorded-footage integration came from the team's local replay and frontend screenshot.
