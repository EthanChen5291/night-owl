# Vision runbook: clips → `pi/rat.onnx` → a node that fires

Owner per plan: Sanjavan; per DEBRIEF: Utsav. Settle at hour 0 (README §6). Whoever it is, this is
the order of operations, with the gates. Every script has `--help`; every gate has a number.

## 0. Environment (Mac)

```
cd vision
uv sync --locked --python 3.12
. .venv/bin/activate
```

Python 3.11+. `ffmpeg` is installed (`extract_frames.py` uses it; `--backend cv2` if not).
Working data lives here and is gitignored: `clips/`, `frames/`, `frames_pruned/`, `labels/`,
`frames_aug/`, `labels_aug/`, `dataset/`, `runs/`, `*.pt`, `*.onnx`, `pi/wheels/`.

## 1. Where the data is this morning

The 09-25 session gave 3,186 kept frames from 19 phone clips, all auto-labelled, 2,176 with at
least one box, 866 pruned (README §4 table). That was done in the working repo; to reproduce here:

```
python3 extract_frames.py --clips clips --tags clips.csv --fps 3 --max-side 960
python3 autolabel.py --conf 0.25                       # YOLO-World, classes 0 rat / 1 person
python3 review.py --unreviewed --order conf            # fix boxes; writes labels/_reviewed.txt
python3 prune.py --blur 60 --dhash 6 --walkin corr_d:0-24 ...
```

`clips.csv` is `filename,tag` (`IMG_7777.MOV,bed_a`); the mapping from IMG_ numbers to tags is
with the clips, not in git. **Review status is now recorded**: `review.py --stats` prints how many
frames are in `labels/_reviewed.txt`. Treat anything not listed there as auto-labelled only.

## 2. Hour-6 gate: a node that fires with zero training

This does not wait for the model. On the Pi, per `pi/README.md`: wheels, `selftest.py`,
`ir_check.py`, then

```
python3 detect.py --model world_rat_person.onnx --color --save-events events
```

Gate: the prop pushed across the floor under IR → an `EVENT` line, a JSON + crop in `events/`, and
(with the server up) `POST ok 200`. The World model scores ~0.80 on the prop, runs ~4× slower than
YOLO11n and fires on hoodies/bags; none of that matters for the gate, it proves the plumbing.

## 3. Rig clips at the venue

Phone footage only covers the rig's domain through the grayscale conversion. Record on the actual
node as soon as it hangs (RECORDING.md, "Once you get there"):

```
python3 grab_frames.py --out rig/hall_a --tag hall_a --seconds 90 --every 5      # on the Pi
scp -r pi@192.168.7.10:~/pi/rig/hall_* frames/                                    # then autolabel + review
```

Also record, as *video* for `eval_events.py`: one clip with 20 pushes and a written list of the
push times (`pushes.csv`, column `t_sec`), and one negatives-only reel (people, hoodies, bags, shoes,
hands, no prop), 3–5 min each. `rpicam-vid -t 180000 --codec mjpeg -o rig_pushes_01.mjpeg` plus the
same settings as `camera.py` is fine; ffmpeg turns it into mp4 on the Mac.

## 4. Train

```
python3 augment_nostring.py --inpaint --per-frame 2 --photometric 1 --exclude-tags stair_e,new_f
python3 make_dataset.py --val-tags stair_e,new_f --extra frames_aug:labels_aug
./train.sh --device mps                     # yolo11n.pt, 416, 60 epochs, batch 32 → runs/rat/candidate.onnx
```

Rules that are not optional:

- **Val is whole clips** (`--val-tags`), never a random frame split; frames within a clip are
  near-duplicates and a random split reports a fake mAP (HANDOFF Q2/Q3). Pick val tags from
  different rooms than train; when rig clips exist, hold out at least one rig clip.
- **Augmented frames never touch val**: `make_dataset.py` drops any augmented frame whose rat
  source or background is a val tag; pass the same tags to `--exclude-tags` so they are not made.
- `GRAY=True` in `make_dataset.py` and `pi/detect.py` must agree (README decision 7).
- Smoke test first: `./train.sh --epochs 3 --name smoke` end to end, then the real run (~20–40 min on an M-series
  Mac with `DEVICE=mps`).

`make_dataset.py` requires a recorded review decision and a label file for every selected frame.
An empty label file is a reviewed negative. For a rushed exploratory run, both
`make_dataset.py --allow-unreviewed` and `train.sh --allow-unreviewed` must be explicit. The
dataset manifest records that choice. Training always exports `runs/rat/candidate.onnx` and
`runs/rat/training_report.json`, even if Gate A fails. It checks ONNX output against PyTorch on
five held-out frames. A failed gate gives exit status 1 and leaves the candidate for diagnosis.

**Gate A: `AP50 rat > 0.9` on the held-out clips**, printed by `train.sh` as `GATE rat AP50`.
Below 0.9: look at `runs/rat/val_batch*_pred.jpg` before touching hyper-parameters; the usual
causes are wrong boxes (review the low-confidence frames), a val clip from a room the model never
saw (fine, that is the point, add rig clips), or the string (Q6, more `--per-frame`).

## 5. Event-level test (the gate that matters on stage)

```
python3 eval_events.py --model runs/rat/candidate.onnx --clip clips/rig_pushes_01.mp4 --pushes pushes.csv \
    --negatives clips/rig_negatives_01.mp4 --conf 0.4,0.5,0.6 --json runs/rat/events.json
python3 promote_model.py --training-report runs/rat/training_report.json \
    --event-report runs/rat/events.json
```

**Gate B: ≥ 18 of 20 pushes produce an event, and < 0.5 false events per minute on the negatives
reel (at least 3 minutes).** The sweep chooses a confidence threshold. Promotion checks both
reports against the same ONNX hash and copies the model plus `rat_config.json` to `pi/`.
`detect.py` reads these measured thresholds for that exact model hash. A failed or incomplete
gate leaves `pi/rat.onnx` alone. Change `--floor-y`, `--min-rat-width`, and `--max-rat-width` on
the eval command to tune those rules; keep `--hits 3` for the demo gate.

## 6. Ship to the node

```
scp pi/rat.onnx pi@192.168.7.10:~/pi/rat.onnx
ssh pi@192.168.7.10 'cd ~/pi && . ~/venv/bin/activate && python3 selftest.py --only detector && python3 detect.py --no-post --max-frames 100'
```

`selftest.py` prints inference time on the Pi CPU; expect 60–120 ms at 416 (5–8 fps after the
camera). If it is over 200 ms, `--threads 4` and check nothing else is running.

## 7. Sunday retrain rule

Retrain on Sunday morning **only if all three hold**: (1) the venue rig clips are labelled and
reviewed (`review.py --stats` shows them), (2) there is a held-out rig clip for val, and
(3) there are ≥ 3 hours before the demo. The retrain is the same commands as §4 with the rig tags
added; keep Saturday's `pi/rat.onnx` as `pi/rat_sat.onnx` and only replace it if Gate B improves
on the same push clip and negatives reel. Never retrain on the pitch morning without Gate B.

## Timeline of gates

| When | Gate | Command |
|---|---|---|
| hour 6 | node fires with the World fallback, POST reaches the server | `detect.py --model world_rat_person.onnx --color` |
| hour ~12 | rig clips recorded, labelled, reviewed | `review.py --stats` |
| hour ~16 | Gate A: rat AP50 > 0.9 on held-out clips | `./train.sh` |
| hour ~18 | Gate B: 20 pushes ≥ 18 events, < 0.5 false/min | `eval_events.py` |
| hour 24 | freeze `pi/rat.onnx` and the constants in `detect.py` | — |
| Sunday am | retrain only under §7 | — |
