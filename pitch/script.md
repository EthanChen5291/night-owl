# Barn Owl: three-minute pitch

Use the live map on slide 2 and the verified recorded-footage replay on slide 4. Try the physical prop only after a fresh Pi test succeeds. Keep the deck visible during the other slides. The spoken text is about 360 words; leave time for the replay.

## 1. Reporting gap, 0:00–0:25

New York has a record of where people report rats. But a 311 call depends on someone choosing to report. Silence on that map does not tell us a block is rat-free. Barn Owl uses another signal: what inspectors find when they sweep blocks and record active rat signs.

## 2. Two signals, 0:25–1:00

We score each block-sized cell two ways. Model A estimates complaints. Model B estimates active-sign risk from physical and environmental features, with no complaint counts. Their percentile gap is our Silence Score. In the current export, East Harlem North has zero complaints in the prior year but ranks tenth out of 5,170 cells on silence. A West Village cell has 31 complaints and lower modeled risk. [Open the live map. Toggle complaints, risk, silence.] These are rankings, not rat counts.

## 3. Backtest, 1:00–1:40

We replayed 119 months. For each month, Model B trained on earlier data. Then we ranked only cells the city actually swept that month and checked the active signs inspectors found. In the top 50, the mean monthly share was 19.5 percent for Model B and 15.2 percent for a ranking by prior 311 calls. That is 4.3 percentage points on this evaluated sample. The chart does not claim we know what happened in unswept cells.

## 4. Node and live trigger, 1:40–2:30

A ranking is a place to start, so the planner proposes tree-pit sites where risk and the data gap are high. We replayed original room-lit camera footage through the exported detector and Pi event rules. One accepted event reached the local API and live map: the score moved from 9.2 to 13.0 percent, and a candidate rose from rank 11 to 2. That verifies the recorded-footage software loop. [Show the replay. Try a physical trigger only if it works in a fresh test, and name which one the audience sees.] The event updates a chosen prior; the city model does not retrain on stage.

## 5. What is real, 2:30–3:00

The city data, cell models, backtest, and recorded-footage map update are real. Teammates report that the Pi camera, PIR, and IR capture work. The room-lit plush model scored .94 AP50 on 22 held-out close-view frames, but .79 across both clips, below our .90 gate. The formal push test and physical Pi inference remain untested. We have no field deployment or rat count. Next is a supervised 50-node pilot checked against later sweeps.

## Presenter guardrails

- The 19.5 and 15.2 percent bars are mean monthly, lot-weighted active-sign shares **within the top 50 swept cells**. They compare rankings on an observed sample, not citywide prevalence or a causal deployment effect.
- The bar labeled Model B is a **risk ranking**, not a Silence Score ranking. The quiet-block analysis is separate.
- The East Harlem North and West Village numbers on slide 2 are model export values for two cells. They are examples, not citywide prevalence or evidence that income caused reporting differences. The screenshot's income and recent-inspection denominators were not reproducible from the available exports, so they are omitted.
- The Pi PIR wakes capture. It does not recognize rats. A successful live event needs the detector, the API, and the map.
- An accepted event updates a chosen Beta prior and may re-rank candidate sites. It does not refit Model B. Model exports also contain historical sweep-informed posteriors; use the API's live event value when speaking about the stage update.
- The toy-rat detector is a prop demo. V1 failed box detection validation (rat AP50 .00755), not an event test. V2 PyTorch and ONNX matched at square 416: .93674 on 22 held-out close-view frames (17 rat boxes), .65108 on 27 separate floor frames (12 rat boxes), and .79031 combined. The combined result missed the >.9 rat gate. These boxes had agent review and no independent human signoff.
- The formal 20-push / 3-minute-negative event gate and physical Pi inference are not evaluated. Keep the saved-video integration result separate from those tests.
- The saved-video integration replay produced exactly one accepted event from original `zoom15_b` footage at 59–63 seconds. Exported ONNX, Pi Detector rules, crop, local API, and frontend map were exercised on a Mac. Score moved 0.0923→0.1297 and plan candidate rank 11→2. This is recorded-footage integration evidence; it does not establish physical Pi performance or the formal event gate.
- The stage prop is lit by room lights. Hardware IR capture and new rig footage do not establish detector performance under IR.
- If the live event is a canned POST or the feed fails, tell the audience exactly which part ran.

## Source snapshot

`model/out/backtest.json`, `model/out/cells.json`, `model/out/metrics.json`, and `vision/TRAINING_RESULTS.md` in this checkout, read 2026-09-26. Hardware status came from `node/DEBRIEF-utsav.md` and the team's later confirmation that the Pi 5 camera is aimed at the table with new IR footage. The recorded-footage integration result came from the team's local replay and frontend screenshot. The plan's older pitch and “What's real” section contain future-tense claims; this script uses the current artifacts.
