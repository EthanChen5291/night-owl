# Night Owl: three-minute pitch

Use the map on slide 2 and the live Pi event screenshot on slide 4. The spoken script is about 325 words.

## 1. Reporting gap, 0:00–0:25

311 shows where people reported rats. It cannot show every place with active rat signs. Night Owl compares complaints with signs that inspectors found on swept blocks.

## 2. Two signals, 0:25–1:00

We score each block-sized cell in two ways. Model A estimates complaints. Model B estimates the share of swept lots with active signs, using building and environmental features but no complaint counts. The gap between their percentile ranks is our Silence Score. In the current export, East Harlem North had zero complaints in the prior year yet ranks tenth of 5,170 cells for that gap. A West Village cell had 31 complaints and lower modeled active-sign risk. [Switch the map between complaints, risk, and silence.] These are model rankings, not rat counts.

## 3. Backtest, 1:00–1:40

We replayed 119 months, training each month on earlier data. Among cells the city swept, Model B's top 50 averaged active signs on 19.5 percent of inspected lots. Ranking by prior 311 calls averaged 15.2 percent. The 4.3-point gap applies only to swept cells. We do not know what inspectors would have found elsewhere.

## 4. Live Pi event, 1:40–2:25

The planner proposes tree-pit sites based on risk and gaps in reporting. Our Pi camera watched a room-lit plush rat for 90 seconds and processed 1,346 frames. Six saved crops showed the plush. We sent one genuine event to the local API. The map moved that site from rank two to one, and its served score from 13.0 to 16.2 percent. [Show the live event screenshot.] One live event made it from the camera to the map. It updated a chosen prior; it did not retrain Model B.

## 5. Detector limits, 2:25–3:00

The detector still needs work. In a fixed recorded test, it alerted on 18 of 19 reviewed plush appearances, but fired 17 false alerts on a cap and shoe in 190 seconds without a plush. That fails our event limit. A separate fresh box test did not establish the 0.90 AP50 target; some reference labels were faulty. This is a room-lit prop demo. We will fix the false alerts and test on new footage before a pilot.

## Evidence for questions

- The 19.5% and 15.2% bars are mean monthly shares of inspected lots with active signs in the top 50 **cells swept that month**. Model B supplied the risk ranking. Silence Score did not rank this backtest. The result does not estimate citywide rat prevalence or a deployment effect.
- East Harlem North and West Village are examples of model output for two cells. The values do not measure prevalence or prove an income effect.
- V5 scored rat AP50 .960806 on its weakest selected development clip after the team reused V4 new-room clips for tuning. A later fixed fresh test scored .615779 rat AP50 as run on 369 frames and did not establish the .90 box target. Source-only review found shifted and oversized reference boxes. Thirty-one proposed corrections were not adopted or rescored, so there is no corrected AP50. AP50 measures box detections, not overall accuracy or event recall.
- In the fixed recorded event test, 18 of 19 source-reviewed plush appearances alerted. The first brief appearance was missed, and the source had 19 appearances rather than the requested 20. All 43 positive event crops showed the plush, including 25 repeat firings. The 190.409-second no-plush clip produced 17 false events, 16 on one cap and one on a shoe. That is 5.357 false alerts per minute against a limit below 0.5. Reviewers checked all 60 emitted crops. The formal event gate failed.
- In a separate 89.859-second live Pi camera observation, V5 processed 1,346 frames at 14.98 frames per second. Reviewers saw the plush in all six saved event crops. The team relayed one event to the local API, which accepted it with HTTP 200. The served score moved .1297→.1618, sightings 1→2, and site rank 2→1. The other five saved events were not posted. This verifies one live camera-to-map event, not reliability across scenes.
- V6 trained for 30 epochs with reviewed hard negatives but failed preset development checks: `table_c` rat AP50 .892 versus .936 required, `table_c` person .801 versus .820, and old-combined person .742 versus .808. The team did not replay V6 or put it on the Pi. V5 remains the demo detector. The failed formal clips are now development material; a later test needs new footage.
- An accepted event updates a chosen Beta prior and can rerank candidates. It does not refit Model B. PIR wakes the camera; the detector decides whether to emit an event. The team has not validated IR footage, wild rats, field deployment, or population counts.

## Sources

[Cell backtest](../model/out/backtest.json) · [cell export](../model/out/cells.json) · [V5 fresh box result](../vision/V5_FRESH_RESULTS.md) · [V5 formal event result](../vision/V5_FORMAL_EVENT_RESULTS.md) · [V6 development plan](../vision/V6_PLAN.md) · [V6 selection check](evidence/v6-checkpoint-selection.json) · [live event receipt](evidence/v5-live-integration-result.json) · [live run stats](evidence/v5-live-run-stats.json) · [live map screenshot](assets/live-pi-map-20260927.png).
