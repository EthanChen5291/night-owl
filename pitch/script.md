# Barn Owl: three-minute pitch

Use the live map on slide 2 and the verified recorded-footage replay on slide 4. Slide 4 shows the physical prototype photographed at the hackathon. Try the physical prop only after a fresh Pi test succeeds. The spoken text is about 320 words; leave time for the replay.

## 1. Reporting gap, 0:00–0:25

311 tells us where people report rats, not where all rats are. Barn Owl adds a second signal: active rat signs found during city inspections of swept blocks.

## 2. Two signals, 0:25–1:00

We score each block-sized cell two ways. Model A estimates complaints. Model B estimates active-sign risk from physical and environmental features, without complaint counts. Their percentile gap is our Silence Score. In the current export, East Harlem North has zero complaints in the prior year but ranks tenth of 5,170 cells on silence. A West Village cell has 31 complaints and lower modeled risk. [Toggle complaints, risk, silence on the map.] These are rankings, not rat counts.

## 3. Backtest, 1:00–1:40

We replayed 119 months, training on earlier data each time. Among cells the city swept, Model B's top 50 averaged 19.5 percent of inspected lots with active signs. Ranking by prior 311 calls averaged 15.2 percent. That 4.3-point gap applies only to swept cells; we do not know what inspectors would have found elsewhere.

## 4. Node and live trigger, 1:40–2:30

The planner proposes tree-pit sites with high risk and a large data gap. In an earlier replay using our V2 detector, one event from recorded room-lit footage reached the API and map. The score moved from 9.2 to 13.0 percent; a site rose from rank 11 to 2. [Show the replay. Name it as recorded footage.] This verifies that software loop for V2. The event updates a chosen prior; the city model does not retrain on stage.

## 5. What is real, 2:30–3:00

The city data, backtest, and earlier map replay are real. Teammates report working Pi camera, PIR, and IR capture. The new room-lit plush detector scored .926 rat AP50 on 59 reserved frames. These adjacent clips share the camera and capture session with training, so new-room performance is unknown. Live Pi detection and formal push testing remain open. We have no field deployment or rat count. Our next proposed test is a supervised 50-node pilot checked against later sweeps.

## Presenter guardrails

- The 19.5 and 15.2 percent bars are mean monthly, lot-weighted active-sign shares **within the top 50 swept cells**. They compare rankings on an observed sample, not citywide prevalence or a causal deployment effect.
- The bar labeled Model B is a **risk ranking**, not a Silence Score ranking. The quiet-block analysis is separate.
- The East Harlem North and West Village numbers on slide 2 are model export values for two cells. They are examples, not citywide prevalence or evidence that income caused reporting differences. The screenshot's income and recent-inspection denominators were not reproducible from the available exports, so they are omitted.
- The Pi PIR wakes capture. It does not recognize rats. A successful live event needs the detector, the API, and the map.
- An accepted event updates a chosen Beta prior and may re-rank candidate sites. It does not refit Model B. Model exports also contain historical sweep-informed posteriors; use the API's live event value when speaking about the stage update.
- The toy-rat detector is a prop demo. The selected V4 checkpoint was trained for 150 epochs, with epoch 33 chosen to keep person AP50 above .84. Matching PyTorch and ONNX scored rat AP50 .958333 on 49 fixed validation frames reused for tuning. The locked ONNX model scored rat AP50 .925806 and person AP50 .876444 on 59 previously unused reserved frames under the square-416 AP protocol. The separate runtime confidence .70 was set using development footage before that test. The reserve consists of four adjacent clips from the same table, camera, and capture session as training; it is not a new-room test. AP50 is a detection ranking metric, not 92.6 percent accuracy or event recall.
- At confidence .50, V4 produced six false events on a development replay. One .70 threshold trial removed those six while retaining 97 reviewed development and 31 consumed-training plush crop events. Those are repeated event firings, not push-level recall or formal event precision. The locked V4 test-video replay has no API POST.
- The formal 20-push / 3-minute-negative event gate and physical Pi inference are not evaluated. Keep the saved-video integration result separate from those tests.
- The earlier V2 saved-video integration replay produced exactly one accepted event from original `zoom15_b` footage at 59–63 seconds. Exported ONNX, Pi Detector rules, crop, local API, and frontend map were exercised on a Mac. Score moved 0.0923→0.1297 and plan candidate rank 11→2. This is recorded-footage integration evidence for V2; V4 has not been verified through the same API path. It does not establish physical Pi performance or the formal event gate.
- A V4 saved-frame Pi timing check measured 56.32 ms median. It does not establish live camera FPS or physical event reliability.
- The stage prop is lit by room lights. Hardware IR capture and new rig footage do not establish detector performance under IR.
- If the live event is a canned POST or the feed fails, tell the audience exactly which part ran.

## Source snapshot

`model/out/backtest.json`, `model/out/cells.json`, `model/out/metrics.json`, `vision/runs/modal-rat-v4-20260926/weak_test_once/verification/verification_report.json`, and `candidate_lock.json` in this checkout, read 2026-09-26. Hardware status came from `node/DEBRIEF-utsav.md` and the team's later confirmation that the Pi 5 camera is aimed at the table with new IR footage. The physical rig photo came from Sanjavan's 2026-09-26 team media. The earlier V2 recorded-footage integration result came from the team's local replay and frontend screenshot.
