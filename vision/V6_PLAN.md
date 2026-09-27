# V6 hard-negative run

**Status: completed and rejected.** This was one bounded development run to reduce the false alerts caused by a dark cap and an edge shoe in the V5 formal no-plush recording. The [V6 result](V6_RESULTS.md) records failed validation guards, so no V6 replay or Pi switch followed. The source clip and its V5 result remain unchanged.

The dataset, source-review files, and run recipe named below are local-only until the V6 evidence bundle is sealed. Their hashes identify the exact inputs; this tracked plan does not contain the frames or labels.

## Frozen data

- Dataset: `vision/dataset_v6/`; freeze: `vision/dataset_v6/freeze.json` at 2026-09-27 05:09:35 UTC.
- 694 train frames and 146 validation frames. The V6 addition is 42 reviewed frames from the full `formal_041054` no-plush clip: 17 person boxes, 25 empty labels, and zero rat boxes. The full source clip is development data and contributes no validation frames.
- Validation keeps whole `zoom15_b`, `table_c`, and `new_room_014327` clips. All 652 original V5 train and 146 validation image/label pairs are byte-identical to V5. The V5 train-pair SHA256 is `8245f4cb09978e9120fdb41b6ac2548ccfd5ef7ac181d5dfd101e82360f41dc2`; the validation-pair SHA256 is `03fde187fddde19df915c9b22947d01ce1f47b47856363540984da2802a29719`.
- Dataset manifest SHA256: `4c93e15d309b1cd4fd8758bf1938642d7f37a95b0023bee18253a0b110bfe515`. Image/label fingerprint: `9346b7f24af41366c3f75cc97339ef22cc8aaecec678edc6134c5fffa5f10335`.
- Original MP4 SHA256: `30c7f71326910f5b182e7af73ae03eb6e43f260ac2c1501814a074c6c7bcc3ec`. Source selection SHA256: `dcd71730ee77532ef40f07335d35cb653c86580bbfc19204cb60f0d3b6ebed2f`. Annotation receipt SHA256: `980fe23d5d2fd7d38e01062d4603ffc4d2918d2310c0bd718bb4d56a488cfa4a`.
- Deterministic three-second whole-frame sampling plus six alert-context timestamps yielded 67 candidates. Codex agents visually reviewed every selected native frame. After the first draft, four connected shoe-and-trouser views received person boxes (`01080`, `01125`, `01394`, `02834`), and eight ambiguous human-boundary views were excluded, including `01591`. The final partition is 42 accepted and 25 excluded. The earlier 50-frame freeze remains locally at `vision/dataset_v6_superseded/`. Local-only `vision/dataset_v6_hard_negatives/empty_label_policy_audit.md` and `review_grids/` record this correction. There was no human signoff.

## Fixed training and checks

The local-only recipe at `vision/runs/modal-rat-v5-20260927/V6_HARD_NEGATIVE_RECIPE.md` starts from locked V5 `best.pt` SHA256 `0906a038d9795e1606d6890627fefe4e4d5eaa4efdadbdb8cab11aaf304b4aa9`. It trains YOLO11n on repeated-channel grayscale at square 416: one Modal L4 job, 30 epochs, batch 8, AdamW, learning rate `5e-5`, `lrf=0.01`, seed 0, patience 30, mosaic 0, scale 0.20, translate 0.08, `hsv_v=0.15`, and horizontal flip 0.5. The job has a 3,600-second cap and zero retries. Ultralytics trainer `best.pt` is the sole checkpoint choice, based on the unchanged V5 whole-clip validation split. Formal clips do not select the checkpoint.

The square-416 CPU PT/ONNX comparison must pass. Predeclared AP50 regression floors are:

| Validation clip | Rat AP50 floor | Person AP50 floor |
| --- | ---: | ---: |
| `zoom15_b` | 0.9597 | undefined |
| `table_c` | 0.9355 | 0.8199 |
| `new_room_014327` | 0.9308 | 0.7541 |
| Old combined (`zoom15_b` + `table_c`) | 0.9519 | 0.8077 |

If those guards pass, the plan replays the consumed formal positive and negative source videos once at the unchanged Pi runtime threshold 0.70. It checks at least the V5 development baseline of 18/19 source-observed plush encounters and at most one event during the 190.409-second no-plush clip. These checks are development regressions. A 0.90 fresh-scene claim still needs new whole-session plush and no-plush recordings, reviewed and frozen before V6 inference. No Pi switch follows automatically.
