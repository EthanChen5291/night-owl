# Recording protocol

Two kinds of footage: the phone session already done (§1) and the rig clips still to record at the
venue (§2). Only the second is in the camera's real domain (NoIR + 850 nm, top-down from a rail).

## 1. What exists: the 09-25 Brown session

**Friday 09-25, 20:36–21:56** (the DEBRIEF and the earlier RECORDING doc say "Thursday"; 09-25 was a
Friday, README §6). 19 phone clips, `IMG_7777.MOV` … `IMG_7800.MOV`, 1080p, mostly landscape, ~30
min total, ~3.0 GB, currently untracked in `~/divMap/` (README §8: move to `vision/clips/`, never
commit). Prop: the Forum Novelties rat, pulled on a string. The clip-to-tag mapping was done by
renaming/copying before extraction; keep it in `clips.csv` from now on.

| Tag | Scene |
|---|---|
| `bed_a`, `bed_b`, `bed_c` | bedroom floor, three angles / light levels |
| `clutter_h` | cluttered floor: bags, shoes, cables (hard negatives with the prop present) |
| `corr_d`, `corr_f` | corridor, long run, person walks in and out (walk-in ranges pruned) |
| `stair_e` | stairwell, prop on treads |
| `stairtop_g` | stair landing from above (closest to the top-down rig view) |
| `r3_a` … `r3_e` | room 3, five short takes at different distances |
| `new_a` … `new_f` | second location, six takes, includes dark-floor takes |

Result after extraction at 3 fps and pruning: 3,186 frames kept, 866 pruned, 2,176 frames with
at least one box. The string is visible in a large share of positives (HANDOFF Q6). No frames
from the rig; the NoIR/IR domain is only covered by grayscale training (README decision 7).

Suggested val tags from this set: `stair_e` and `new_f` (different rooms from the bulk of train).

## 2. Once you get there: rig clips at the venue

Do this as soon as the node hangs, before training, in this order. Everything goes through
`pi/grab_frames.py` (frames) or `rpicam-vid` (video for the event test). One tag per take.

### Positions

| Take | Tilt (sector plate) | Height | Tag |
|---|---|---|---|
| straight down over the "pit" | 0° | 60 cm rail (or the diorama's 25 cm) | `rig_down_a` |
| 45° toward the far rail | 45° | same | `rig_tilt_a` |
| the demo position, whatever you settle on | as set | as set | `rig_demo_a`, `_b` |

Rats run along the inside of the guard, so the 45° take is the one the demo will look like.
Record each position once with the room lights on and once off.

### Lighting

- `ir_check.py` before each take; note the verdict in the take name (`rig_demo_a_ir`, `rig_demo_a_amb`).
- IR on, room dark: the demo condition. IR off, room lit: what the venue hall will be during setup.
- Expect the magenta cast in colour and the prop's glass eye glinting under IR (README §4, pitch:
  phrase the "eyeshine" line so the demo crop does not contradict it).

### Negatives (no prop in frame): at least 3 minutes per position

Hoodies (dark, dropped on the floor and worn while walking past), backpacks and tote bags, shoes
(single and pairs), hands reaching into frame, feet walking through, a phone on the floor, a
crumpled dark jacket. These are what the World fallback fires on; the trained model must not.
Save the negatives as a *video* too (`rpicam-vid -t 180000 --codec mjpeg -o rig_negatives_01.mjpeg`)
for `eval_events.py`.

### Pushes (the positive event clip)

One 3–5 minute video, 20 pushes of the prop across the floor with a 5–10 s pause between them.
One person pushes, one person writes down the time of each push from the clip's start (or claps in
frame so the time can be read from the video later). That list is `pushes.csv`, column `t_sec`,
one row per push. Mix directions, speeds, and distances from the camera; include 3–4 pushes with a
foot or hand in the frame at the same time (person suppression must not kill the event).

### Naming and where it goes

```
rig/<tag>/<tag>_00000.jpg ...        grab_frames.py output on the Pi
clips/rig_pushes_01.mp4              push clip (mjpeg → mp4 on the Mac with ffmpeg -c:v libx264)
clips/rig_negatives_01.mp4           negatives reel
pushes.csv                           t_sec[,label]
```

`scp` the `rig/` folders into `frames/`, run `autolabel.py`, `review.py --tag rig_demo_a` (review
every rig frame: the auto-labels have never seen this domain), then hold out one rig tag as val.

### Time budget

30 minutes total at the venue: 10 for positions and IR, 10 for negatives, 10 for the push clip.
Do not skip the negatives reel; Gate B in the RUNBOOK cannot be measured without it.
