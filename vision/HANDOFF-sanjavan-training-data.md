# Training-data questions for Sanjavan (historical)

This 09-25 handoff records early phone-footage choices. Its defaults are no
longer the current Night Owl detector recipe. The model now uses YOLO11n on
grayscale full frames with rat and person classes. Use the [runbook](RUNBOOK.md)
for current commands and the [V5 formal event result](V5_FORMAL_EVENT_RESULTS.md)
for the failed no-plush test. Keep the questions below as a record, not a plan
to relabel frozen test footage.

Written 09-25 evening, rebuilt 09-26. Each question describes its context,
default at the time, and the decision then needed.

## Data state this morning

| | Count |
|---|---|
| Frames kept in `frames/` | 3,186 |
| Frames moved to `frames_pruned/` (blur / walk-in / duplicate) | 866 |
| Label files | 3,186 |
| Label files with at least one box | 2,176 |
| Clip tags | 19 (bed_a/b/c, clutter_h, corr_d/f, stair_e, stairtop_g, r3_a–e, new_a–f) |
| `dataset/`, `runs/rat/`, `pi/rat.onnx` | absent → **not trained** |

All frames are phone footage (1080p, 3 fps, downscaled to 960); no rig frames exist. Labels are
YOLO-World auto-labels (`autolabel.py`, conf 0.25); whether `review.py` ran over all of them is
not recorded (label files touched 21:59, after pruning at 21:22, so at least a pass happened).
From now on `labels/_reviewed.txt` records it; `review.py --stats` prints the count.

## Q0. Detector vs crop classifier

**Context.** The master plan specified a 96×96 crop classifier fed by frame-diff crops from
picamera2's dual stream. picamera2 is not installed on the Pi and the Pi is offline, so the build
switched to a YOLO11n detector on the whole 640×480 frame via `rpicam-vid` + onnxruntime (README
decision 5). YOLO localises in one pass and gives the bbox the contract wants; it costs ~4× the
compute of a tiny classifier and needs box labels rather than crop labels.
**Default.** YOLO11n, 416, grayscale, ONNX, `pi/detect.py`.
**Decision.** Keep the detector, or go back to a classifier on motion crops (which means writing
a frame-diff cropper in numpy and re-labelling as crops). The pipeline and the Pi code are built for
the detector; switching costs the morning.

## Q1. Prop-only vs real rats

**Context.** Every positive is the Forum Novelties prop. Real rat footage (public datasets, YouTube)
differs in fur texture, gait, tail and IR reflectance, and would make the model honest about the
roadmap claim, but the demo is the prop under IR on stage and mixing domains with a 3k-frame set
risks the demo.
**Default.** Prop-only for the demo model (README decision 6); real rats as a roadmap experiment.
**Decision.** Confirm prop-only. If you want a real-rat sanity check, do it as a separate val-only
folder and report the number on the "What's real" slide, do not train on it.

## Q2. Correlated frames

**Context.** 3 fps from ~30 min of video is 3,186 frames of ~19 scenes. Consecutive frames are
near-duplicates; `prune.py` removes exact runs (dHash < 6) but neighbours 1–2 s apart are still
highly correlated. The effective dataset size is closer to the number of *scenes × distinct prop
positions* than to 3,186.
**Default.** Keep all kept frames; rely on the tag-level split (Q3) to keep the metric honest.
**Decision.** Is further thinning worth it (e.g. `--dhash 10`, or keep every 2nd frame) to trade
duplicates for training speed? The model does not get worse from duplicates, the mAP just gets
optimistic if the split leaks, and the split does not leak.

## Q3. Stratified val split

**Context.** A random frame split puts near-identical frames in train and val and reports a mAP in
the high 0.9s that means nothing. `make_dataset.py` therefore splits by clip tag (val = whole clips)
and drops augmented frames that touch a val tag. Suggested val: `stair_e`, `new_f` (~15–20% of
frames, different rooms). Once rig clips exist, at least one rig tag must be in val, because that
is the domain the gate is about.
**Default.** `--val-tags stair_e,new_f`.
**Decision.** Confirm the tags, or pick others. Also: should val be *only* rig clips once they
exist (honest, but tiny), or rig + two phone clips (more stable number)?

## Q4. Autolabel bias on dark floors

**Context.** YOLO-World at conf 0.25 misses the prop on dark floors and in the dim `new_*` takes,
so those frames have empty label files and enter training as *negatives that contain a rat*. That
teaches the model to miss exactly the frames that look like the IR demo. `labels/_autolabel.csv`
has the per-frame max confidence; `review.py --order conf` shows the lowest first.
**Default.** Empty-label frames are kept as negatives, capped at 1:1 with positives
(`--max-empty-ratio 1.0`).
**Decision.** Either (a) review every empty-label frame from the dark tags and draw the missing
boxes (an hour), or (b) `--drop-empty` and train with no negatives from phone footage, using only
the rig negatives reel as negatives. (a) is better if the hour exists.

## Q5. Whether `person` earns its keep

**Context.** Class 1 exists so `detect.py` can suppress rat boxes overlapping a person (feet,
hands, a dropped hoodie a person is standing on). It costs label noise (auto-labelled people are
often partial: legs only) and a share of the model's capacity. The alternative is a single-class
model plus the floor rule and the hit counter, with hoodies and bags handled by negatives.
**Default.** Two classes; `detect.py` drops a rat box with IoU > `PERSON_IOU` (0.3) against a person
box *or* with more than `PERSON_CONTAIN` (0.7) of its area inside one (IoU alone never reaches 0.3 for a
small box inside a big one, e.g. feet standing over the prop).
**Decision.** Keep `person`, or drop to one class (`make_dataset.py` would need a `--classes 0`
filter, a five-line change; `detect.py` already copes with a model that never outputs a person).
The negatives reel from the venue answers this empirically: run `eval_events.py` with both.

## Q6. Synthetic paste positives (and the string)

**Context.** The prop is pulled on a thin string that is visible in most positives; a small model
will learn it. `augment_nostring.py` inpaints the strip where the string enters the box, cuts the
prop out and pastes it onto negative frames (random scale/flip/brightness, feathered edge, centre
below `FLOOR_Y`), plus photometric-only copies. Paste positives are cheap but their boundary
statistics differ from real frames; too many and the model learns "pasted blob".
**Default.** `--per-frame 2 --photometric 1 --inpaint`, train only, val tags excluded.
**Decision.** Use them at all; how many per frame; whether to paste onto rig negatives once they
exist (the highest-value backgrounds). Compare Gate A with and without `--extra`.

## Q7. Event-level metric

**Context.** mAP is a box metric; the demo is an event: prop pushed → one event, no prop → nothing.
`eval_events.py` replays the exact `detect.py` logic (floor rule, person suppression, 3 hits in
1 s, 2 s cooldown) over a push clip with ground-truth push times and a negatives reel and reports
pushes hit, false events, and false events per minute, sweeping `CONF`.
**Default.** Gate B = ≥ 18/20 pushes, < 0.5 false events / min. Window ±(0.5 s before, 3 s after)
a push counts as a hit.
**Decision.** Agree the gate numbers and the window. Decide whether `HITS_NEEDED=3` in 1 s at the
Pi's ~6 fps is right (that is 3 of ~6 frames), or whether it should be 2 hits / 0.7 s for a fast
push.

## Q8. Sunday retrain rule

**Context.** Venue rig clips arrive Saturday; a retrain with them in is the single biggest
improvement available, and the single biggest way to break a working demo on Sunday morning.
**Default.** RUNBOOK §7: retrain only if rig clips are labelled *and reviewed*, a rig clip is held
out, and ≥ 3 h remain; keep Saturday's ONNX as `rat_sat.onnx`; swap only if Gate B improves on the
same push clip and negatives reel.
**Decision.** Confirm, or set a hard freeze at hour 24 with no Sunday retrain at all.

## Q9. Anything else you find important

Things noticed while rebuilding, in case they matter to you:

- `FLOOR_Y=0.40` was chosen for a side-facing camera; face-down at 0° the whole frame is floor and
  the rule drops nothing, at 45° the top ~40% is the far rail/wall. Re-check on the first rig frame.
- The World fallback exports with `imgsz 416` but was not trained gray; `detect.py --color` for it.
- The pruned walk-in ranges were set by eye per tag and are not in git; `prune.py --walkin` takes
  them explicitly now, write them into the RUNBOOK when you re-prune.
- The IMG_ → tag mapping lives only with the clips. Put it in `clips.csv`.
- Nothing in the pipeline uses the PIR. If the demo wants "PIR wakes the detector", that is a
  10-line change in `detect.py` (`gpiozero.MotionSensor(4)`, only run inference while `.motion_detected`
  or for 5 s after), and it halves the false-event rate for free. Worth deciding before Gate B.
