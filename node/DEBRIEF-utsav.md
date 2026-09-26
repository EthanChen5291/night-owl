# DEBRIEF for Utsav — joining remote, Saturday 09-26

You are joining a team of four at DivHacks 2026 (Columbia, Sept 26–27, Hack the City track) from off
site. This is the narrative version of the repo README: what we are building, why, what already exists,
what this document asks you to own, and what to do in your first two hours. Read it top to bottom once,
then the README, then the two files in "Read first".

Note on dates: the original DEBRIEF and the recording notes said the recording session was "Thursday".
It was **Friday 09-25** (20:36–21:56 at Brown). Same session, wrong weekday; nothing else changes.

## 1. What the project is

**Barn Owl** (called "Silent Blocks" until Friday evening; "silent block" is still the name of the thing
the model finds). Domain: ratst.at.

NYC's public rat map is built from 311 complaints. That is a map of *who complains*, not of where rats
are. Some neighbourhoods call 311 for everything; others never do. The Health Department also runs
inspections, and those split into complaint-driven visits and **proactive ("indexed") visits** that the
city schedules regardless of calls. The proactive ones are roughly 130k near-unbiased outcomes a year:
someone went to a lot with no complaint on it and recorded whether there were active rat signs.

Ethan's P0 check on the real data (README §4) confirmed the premise: 75–91% of Initial inspections have
no prior 311 complaint on that lot, and complaint-linked inspections find active rats **2–3× as often**
(≈40% vs 15–20%). That gap *is* the selection bias, in one number.

So we train two models per H3 resolution-9 hex cell × month:

- **Model A** predicts complaints from all features: "what the city sees".
- **Model B** predicts P(active rat signs | inspected) from physical/environmental features only, with
  inverse-propensity weights and never any complaint counts: "what is there".
- **Silence Score** = percentile(B) − percentile(A). A **silent block** is high B, low A: rats likely,
  nobody calling. The validation is a backtest on real inspections (rolling-origin, one chart).

Then the hardware angle: a small Pi 5 camera node hangs from a tree-guard rail, watches the tree pit
where rats run, and when it detects one it posts a tiny JSON event. Each event updates the cell's
Beta-Binomial posterior. The sensor turns the ranking into evidence, and gives the judges something
physical to trigger on stage.

Must ship (in this order): (1) the map with a "city sees / actually there" toggle, (2) the backtest
chart, (3) a live node trigger on stage.

## 2. What the node does

Hardware: Raspberry Pi 5, Arducam IMX219 **NoIR** camera (no IR-cut filter, so it sees infrared), one
850 nm IR illuminator on its own power bank, and an HC-SR501 PIR motion module on GPIO4. It mounts
face-down from an L-arm clamped to the rail (enclosure design "D3"), tilt set by an indexed plate.

Flow: PIR wakes the pipeline → `rpicam-vid` streams 640×480 grayscale frames → a YOLO11n detector
(ONNX, CPU) looks for a rat (actually a Forum Novelties rat prop; we are honest about this) → three hits
in a row → one event, max one per 2 s → `POST /event` with node id, H3 cell, timestamp and a base64
crop → the backend bumps the cell posterior → the map updates. The images under IR look **magenta**;
that is normal for a NoIR sensor and we train and run in grayscale so phone footage and rig footage
share one domain.

Two constraints that shaped everything: the Pi **has no internet** (campus Wi-Fi is 802.1X) and
`picamera2` **is not installed**. So no pip on the Pi (offline wheels for Python 3.13 aarch64 instead),
no Python camera API (shell out to `rpicam-*`), and no frame-diff crop classifier as the plan wanted
(YOLO localises in one pass instead). Also: the PIR does *not* detect rats; it is a wake-up gate.

## 3. What exists (as of Saturday morning)

| Workstream | State |
|---|---|
| Data | Done. 17 open-data sources baked to Parquet; `data/SCHEMA.md` documents every column; P0 finding above. |
| Model | Not started (MLH: Saturday work). Spec in `plan/master-plan.md` §4. |
| Frontend | A three.js city renderer of Lower Manhattan with an H3 overlay exists, fed by a **synthetic** fixture in the frozen `GET /cells` shape. No API yet. Plan said deck.gl + MapLibre; nobody has built that. |
| Node hardware | Verified 09-23: camera, PIR, PIR-triggered IR capture, video stream all pass. 25 IR captures in Bruno's repo. |
| Enclosure | D3 designed, fit-checked, STLs exported, **not printed**. IR board unmeasured. |
| Vision | Pipeline scripted and dry-run on the Mac. 3,186 frames extracted from 19 phone clips, 2,176 with boxes, labels partly reviewed. **Nothing trained.** A YOLO-World zero-training fallback exists (works, slow, false-positives on hoodies). No footage from the actual rig yet. |
| Pitch | 3-minute script and Q&A one-liners in `plan/master-plan.md` §10. **Deck not started.** |

## 4. What this document asks you to own, and the conflict

Per this DEBRIEF: **the detector and the deck.**

Per the master plan: **the frontend** (map), with Sanjavan on vision.

Both documents are in the repo and they disagree; the README lists this as the first thing to settle at
hour 0. The reason this DEBRIEF hands you the detector is practical: it is the workstream that a remote
person can drive entirely on a laptop with the footage (training happens on a GPU box or Colab, not on
the Pi), and the deck is naturally remote work too. The frontend, by contrast, needs to be wired to
Ethan's API as it lands, which is easier in the room. But Sanjavan has the training-data questions
addressed to him (`vision/HANDOFF-sanjavan-training-data.md`) and may already be on it.

**Do not pick unilaterally.** Ask in the group chat at hour 0: "Am I detector + deck, or frontend?"
Either way, the deck is yours: nobody else has time for it, and it is the thing that gets judged.

The rest of this file assumes detector + deck. If it is frontend, the relevant README section is §4
"Frontend / map" and your hour-6 target is hexes rendering from `city/cells.fixture.json`.

## 5. Where files are

Two working repos on Ethan's Mac, and this clean-room rebuild:

- **This repo** (the rebuild; everything event-day is committed here): `plan/`, `data/`, `city/`,
  `node/`, `enclosure/`, `vision/`, `renders/`. All docs and scripts, no binaries.
- `~/divMap` → `github.com/EthanChen5291/ratstat` (private): the Parquet data, the three.js app, the
  Gemini render tool, `.env` with `GEMINI_API_KEY`. Also, wrongly, the 19 phone clips `IMG_7777.MOV` …
  `IMG_7800.MOV` (~3 GB), which Ethan is moving.
- `~/div-hacks-26` → `github.com/brubru6707/div-hacks-26` (Bruno's): the Pi handoff, `captures/`, the
  enclosure CAD (`enclosure/`, on an unpushed local branch), and **the whole vision pipeline including
  frames and labels** (`vision/`, untracked as of this morning; Ethan is pushing it).

For you, remote, the practical answer is: the scripts come from this repo; the frames, labels and clips
have to be sent to you (or you re-extract from the clips). Ask Ethan for a zip of
`vision/frames/`, `vision/labels/` and the clip list, or a shared-drive link, in your first message.

Vision files you will touch, all under `vision/`:

- `RUNBOOK.md`: the step-by-step (extract → prune → augment → make_dataset → train → export → Pi).
- `RECORDING.md`: how the clips were shot, the 19 clip tags, and "Once you get there" for rig clips.
- `HANDOFF-sanjavan-training-data.md`: the ten open questions Q0–Q9. Answer them or agree with Sanjavan.
- `make_dataset.py`, `train.sh`, `pi/detect.py`, `pi/camera.py`, `pi/selftest.py`.
- `pi/wheels/` (not in git) and `pi/world_rat_person.onnx` (the fallback, 50 MB, not in git).

## 6. Read first, in this order

1. `README.md` (this repo root), all of it. Twenty minutes.
2. `vision/RUNBOOK.md` and `vision/HANDOFF-sanjavan-training-data.md`.
3. `plan/master-plan.md` §10 (the pitch script) and §12 ("What's real" slide). The deck is built
   around these.
4. `node/HANDOFF-pi5-camera-pir-node.md`, only the magenta section and the "eyeshine" note, so the
   deck's demo crop and its caption do not contradict each other.

## 7. First three tasks

1. **Settle the role at hour 0** (see §4) and get the data: frames + labels zip, the clip list, and
   confirmation of what `review.py` has been run over. Until someone confirms, treat the labels as
   reviewed-in-part.
2. **Train a first YOLO11n** on what exists: `make_dataset.py` (grayscale, 416 px, stratified val split
   *by clip*, not by frame, because consecutive frames are near-duplicates), `train.sh`, export to
   ONNX. Target for the hour-6 gate is simply "a `pi/rat.onnx` that fires on the prop in held-out
   clips"; the real gate is mAP50 (rat) > 0.9 on held-out clips and, better, the event-level test
   (20 demo pushes, plus a negatives-only reel that must produce zero events). Send `rat.onnx` to Bruno
   to drop on the Pi. If training is not going by hour 4, say so: the YOLO-World fallback is the plan B
   and the stage demo does not need your model to exist.
3. **Start the deck** from the script in the plan. Skeleton first: problem (the 311 map is a complaint
   map) → the P0 number (2–3×) → two models and the silence score → the backtest chart (placeholder
   until Ethan's model lands) → the node (renders in `renders/`, the D3 enclosure, one IR capture) →
   live demo → "What's real" slide → roadmap. Claims to be careful with: it is a *risk ranking*, not a
   rat population estimate; the PIR is a wake-up, not a rat detector; the detector is "a prop detector
   trained on ~N frames from the rig"; the prop's glass eye glints under IR, so phrase the eyeshine
   line so the crop does not contradict it. The cyan glow in the renders is demo-only; a field node is
   dark.

After those: retrain on rig clips once Bruno records them at the venue (Sunday retrain rule in Q9),
Devpost text, the 2-minute video, and rehearsal timing.

## 8. How to reach the team

- Group chat: the team thread (Ethan adds you; if you are reading this and are not in it, message
  Ethan). Post there rather than DMing, so nobody repeats work.
- **Ethan** (data, model, repo, renders): anything about the repos, the data, `GEMINI_API_KEY`, the
  clips and frames. He is the one committing this rebuild.
- **Bruno** (hardware, Pi, printing): the Pi login (`CREDENTIALS.txt`, not in any repo), putting
  `rat.onnx` on the Pi, recording rig clips at the venue.
- **Sanjavan** (vision / backtest): the Q0–Q9 answers, label review status, and whether he is taking
  the detector instead of you. Talk to him before you train.

Hour markers in the plan are from the event start (Saturday morning). Hour 24 is the freeze; 24–28 is
deck, Devpost, video, one-pager; 28–32 is rehearsal. Anything you make, commit to this repo under your
own name (MLH rule: event work must be the team's own commits, at the event).
