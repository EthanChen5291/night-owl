# NightOwl recording protocol

Capture the original video from the Pi camera agent. The current detector targets a dark plush rat in a lit tabletop view. Infrared and live rats are separate, unvalidated conditions. Do not start a second camera process beside `/home/pi/barn-owl/agent.py` to collect footage; use the agent's recording workflow and preserve the original file bytes.

## Set up the view

Record the camera position, lighting, table surface, and whether the whole plush can cross each frame edge. Keep those details with the clip. V5 alerted late when the plush entered partly from the lower-right edge; include that position in new *training* footage if the goal is to improve edge detection. It also fired on a dark logo cap and a partial shoe in a no-plush clip. Include those objects, people, and clothing in training negatives, with full-frame review.

Collect whole recordings, not isolated detector crops. For each original, save its SHA256, capture start, duration, decoded frame count, and per-frame presentation timestamps. Use a distinct source tag for each take. Keep every frame from one source session in one split; adjacent frames are too similar for a random train/validation split.

## Record a new event test

Freeze a test plan and reserve the whole clips before the new model sees them. Record:

1. A lit positive clip with at least 20 **visibly distinct** plush entrances and exits. Aim for a few extra passes so an occluded or end-censored attempt does not leave fewer than 20 complete source appearances. Leave clear empty gaps. Vary direction and speed; include edge entries and people where relevant. Do not choose the easiest 20 afterward.
2. A separate no-plush recording lasting at least 180 seconds. Keep the camera running through ordinary motion and clutter: cap, shoes, dark garments, bags, hands, and people. Avoid moving the plush anywhere visible in this clip. Do not assemble three minutes from gaps in the positive recording.

Before inference, reviewers inspect the original positive video and mark every observed appearance by its decoded source timestamp, including ambiguous and censored intervals. Reviewers inspect the no-plush video across its full timeline and record their sampling coverage and remaining limits. Freeze those notes and file hashes. For box AP, sample frames under a rule fixed before predictions and review every full-frame plush and person label; an empty YOLO file is a reviewed no-class frame, not a missing annotation.

Run the locked model once on every decoded frame at its frozen confidence, NMS, person filter, and three-hit event rule. Match at most one emitted event to each complete source appearance. Audit **every** emitted crop against its native source frame before calling it a plush or false event. The formal target is at least 18 detections among at least 20 complete pushes, and fewer than 0.5 false events per minute over the separate three-minute no-plush recording. More than one alert on a parked plush is still one appearance.

The V5 formal recording had 19 complete appearances and 17 false events in 190.409 seconds, mostly on one cap. It failed. Its footage was later used to build the V6 hard-negative dataset, so another model needs a new reserved recording. See [V5 formal event results](V5_FORMAL_EVENT_RESULTS.md), [V6 results](V6_RESULTS.md), and the current [runbook](RUNBOOK.md).

## Earlier phone footage

The 09-25 Brown session had 19 phone clips named within the `IMG_7777.MOV` to
`IMG_7800.MOV` range. The original `clips.csv` mapped those filenames to tags
such as `bed_a`, `clutter_h`, `corr_d`, `stair_e`, `stairtop_g`, `r3_a`, and
`new_a`. The early extraction kept 3,186 frames after pruning 866. Those
phone clips predate the current Pi camera dataset and do not provide a fresh
NightOwl test. The historical [training-data handoff](HANDOFF-sanjavan-training-data.md)
records the original questions and clip groups.
