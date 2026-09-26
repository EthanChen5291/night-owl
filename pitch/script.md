# Barn Owl: three-minute pitch

Use the live map on slide 2 and the physical prop on slide 4. Keep the deck visible during the other slides. The spoken text below is about 365 words; leave roughly 20 seconds for the live trigger.

## 1. Reporting gap, 0:00–0:25

New York has a record of where people report rats. But a 311 call depends on someone choosing to report. Silence on that map does not tell us a block is rat-free. Barn Owl uses another signal: what inspectors find when they sweep blocks and record active rat signs.

## 2. Two signals, 0:25–1:00

We score each block-sized cell two ways. Model A estimates complaints. Model B estimates active-sign risk from physical and environmental features, with no complaint counts. Their percentile gap is our Silence Score. In the current export, East Harlem North has zero complaints in the prior year but ranks tenth out of 5,170 cells on silence. A West Village cell has 31 complaints and lower modeled risk. [Open the live map. Toggle complaints, risk, silence.] These are rankings, not rat counts.

## 3. Backtest, 1:00–1:40

We replayed 119 months. For each month, Model B trained on earlier data. Then we ranked only cells the city actually swept that month and checked the active signs inspectors found. In the top 50, the mean monthly share was 19.5 percent for Model B and 15.2 percent for a ranking by prior 311 calls. That is 4.3 percentage points on this evaluated sample. The chart does not claim we know what happened in unswept cells.

## 4. Node and live trigger, 1:40–2:30

A ranking is a place to start, so the planner proposes tree-pit sites where modeled risk and the data gap are high. Our Pi 5 node looks down through a NoIR camera. PIR wakes it; the camera detector makes the call. [Move the toy rat under the node. Wait for the event.] The event sends the cell, confidence, and a crop. The API updates that cell's chosen prior and re-ranks candidates. We are updating the displayed score, not retraining the model on stage. [Point to the feed and changed value only if they appear.]

## 5. What is real, 2:30–3:00

The city data, cell models, backtest, and Pi camera and IR capture are real. Today's detector is for this toy rat, and its held-out rig tests are still pending. We have not deployed a field network or counted rat populations. Our next step is a supervised 50-node pilot and a comparison with later sweeps. Barn Owl gives inspectors a better question to ask: where should we look next?

## Presenter guardrails

- The 19.5 and 15.2 percent bars are mean monthly, lot-weighted active-sign shares **within the top 50 swept cells**. They compare rankings on an observed sample, not citywide prevalence or a causal deployment effect.
- The bar labeled Model B is a **risk ranking**, not a Silence Score ranking. The quiet-block analysis is separate.
- The East Harlem North and West Village numbers on slide 2 are model export values for two cells. They are examples, not citywide prevalence or evidence that income caused reporting differences. The screenshot's income and recent-inspection denominators were not reproducible from the available exports, so they are omitted.
- The Pi PIR wakes capture. It does not recognize rats. A successful live event needs the detector, the API, and the map.
- An accepted event updates a chosen Beta prior and may re-rank candidate sites. It does not refit Model B. Model exports also contain historical sweep-informed posteriors; use the API's live event value when speaking about the stage update.
- The toy-rat detector is a prop demo. Replace “held-out rig tests pending” with a measured result only after the clip and event evaluation is complete.
- If the live event is a canned POST or the feed fails, tell the audience exactly which part ran.

## Source snapshot

`model/out/backtest.json`, `model/out/cells.json`, and `model/out/metrics.json` in this checkout, read 2026-09-26. Hardware status came from `node/DEBRIEF-utsav.md` and the team's later confirmation that the Pi 5 camera is aimed at the table with new IR footage. The plan's older pitch and “What's real” section contain future-tense claims; this script uses the current artifacts.
