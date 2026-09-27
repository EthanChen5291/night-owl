# Plush detector candidate bundles

The latest **development candidate** is [rat-litroom-v5-development-candidate-20260927.zip](rat-litroom-v5-development-candidate-20260927.zip), SHA256 `5d4098dfea86dc80de230f9a689dad4ccdf819c194ac2ba5cdf96185bd5ca38e` (94,422,665 bytes). Its extracted `README.md` and `verify_bundle.py` describe and check all 2,261 other files. A clean extraction passed CRC, per-file checksums, and model/lock hash checks. V5 was trained from V4 on reviewed new-room development data. Its selected epoch-35 ONNX passed the predeclared whole-clip development AP floors and fixed-rule replay audits, including the previously missed parked plush. A fresh post-lock recorded-video test has since failed to establish the 0.90 target, so the model remains a candidate and is not promoted to `pi/rat.onnx`. See [V5 results](../V5_RESULTS.md) and the [fresh-test results](../V5_FRESH_RESULTS.md) for scores and limits.

The later [V6 hard-negative run](../V6_RESULTS.md) is **rejected**. It trained on 42 reviewed frames from the previously failed formal no-plush clip, then missed predeclared `table_c` rat and person guards and the old-scene combined person guard. PT/ONNX parity passed, but no V6 full-video replay or Pi switch occurred. Its frozen data, failed import attempt, one recovery, model, reports, and post-run warmup diagnosis are preserved in two archives. Extract both into the same parent directory and run `python3 verify_bundle.py` inside the extracted directory. Root verified both ZIP CRCs and all 1,839 file hashes. These archives preserve a failed experiment; V5 remains the limited demo candidate.

| V6 evidence archive | Bytes | SHA256 |
| --- | ---: | --- |
| [Model, dataset, code, and reports](rat-litroom-v6-development-candidate-20260927.zip) | 72,769,313 | `8ff2246855981c5b332c160e91d4bfde0d7a20d771afbecb16fd6d65c30579ce` |
| [Source frames and review grids](rat-litroom-v6-development-candidate-20260927-source-review.zip) | 29,570,970 | `fb02a2e90bd0cb35a7529c215a4b991ec38665a36a744406129fc02a946188e7` |

The fresh-test evidence is split into [core](rat-litroom-v5-fresh-test-evidence-20260927.zip), SHA256 `d81d8b66672809943e483fccc03f729d43e38937d63d162c99bd3f1e67da35f3` (82,553,894 bytes), and [source-review images](rat-litroom-v5-fresh-test-evidence-20260927-source-review.zip), SHA256 `122a5be2d353d4afc9708b9d751b6ef125a466d901db39dcd76c8592e12d9ba7` (30,364,626 bytes). Extract both into the same parent directory, then run `python3 verify_bundle.py` inside `rat-litroom-v5-fresh-test-evidence-20260927/`. A clean extraction verified all 2,395 listed files and both ZIP CRCs. The archives preserve the original rat AP50 **0.615779**, its annotation-quality caveat, 34 plush event crops, zero events in the 175.937-second negative clip, and 31 unadopted draft label proposals. The negative clip is shorter than three minutes and the source review contains only two complete plush-presence episodes, so the formal event gates remain incomplete. The included `replay_video.py` is the original first-run source snapshot. The V5 model ZIP above is unchanged.

The later [formal event-test evidence](rat-litroom-v5-formal-event-evidence-20260927.zip), SHA256 `518f0a9c0c4aef94ee7f6a3ae318613fbc37e6689d8d9dfe2d8dfa40a98eb75f` (83,371,421 bytes), preserves two new original videos, frozen source intervals, the first locked replay, all 60 event crops, and their independent visual adjudication. ZIP CRC and all 509 packaged SHA256 entries passed. The [formal result](../V5_FORMAL_EVENT_RESULTS.md) failed: 18 of 19 source-reviewed plush appearances received an alert, while the no-plush clip produced 17 false alerts, chiefly on a baseball cap. The model and threshold were not changed after this test.

The separate [live integration evidence](rat-litroom-v5-live-integration-evidence-20260927.zip), SHA256 `cc28bf4506c3f3d70a8619775153a9b2dc69fa2f07c5c419574bdb79e30f5e0f` (169,364 bytes), records one coordinated plush-to-local-map check. Six crop-only alerts showed the same visible plush; only the first was relayed, accepted once, and moved the selected demo cell from score 0.1297 to 0.1618 and plan rank 2 to 1. ZIP CRC and all 33 packaged SHA256 entries passed. See [live results](../V5_LIVE_RESULTS.md). This integration check does not change the failed formal test or promote V5.

The V4 recorded-footage candidate remains [rat-litroom-v4-candidate-20260927.zip](rat-litroom-v4-candidate-20260927.zip). Its separate [new-room evaluation supplement](rat-litroom-v4-new-room-evaluation-20260927.zip), SHA256 `8e9a126fc1360bae1a19378d46743f96a31a8a361650288b55d1b34b895d7661`, preserves the failed first post-lock new-room check. Both V4 archives are unchanged. The V5 ZIP references their original source videos by SHA rather than duplicating those recordings.

## V4 bundle history

The V4 model bundle contains the locked V4 ONNX and PyTorch model, all reviewed grayscale training/validation frames and labels, source and package lockfile, checkpoint selection and training curves, CPU evaluation reports, original development and reserved videos, truth/provenance, replay crops, and a Raspberry Pi saved-frame timing report. It is a **candidate for a lit metal-table plush demo**, not a promoted detector for live rats.

## Extract and verify

From the repository root:

```sh
unzip vision/artifacts/rat-litroom-v4-candidate-20260927.zip -d /tmp/barn-owl-v4
cd /tmp/barn-owl-v4/rat-litroom-v4-candidate-20260927
python3 verify_bundle.py
```

The ZIP has 2,193 files, is 91,067,807 bytes, and has SHA256 `8757ba863b0b20618f49b817059bec9a6af0d5d4268126f0f46e4704de4cecc7`. The extracted checksum script verifies all 2,192 listed files, including the verifier. Extraction, checksum verification, and the bundled reserved-test source/provenance check passed on a clean temporary directory. The extracted `README.md` gives the exact model hashes, recorded results, and a `--no-post` Pi dry-run command at locked confidence 0.70. Keep the model under a distinct filename; do not replace `pi/rat.onnx` until formal promotion gates pass.

## Evidence and limits

The repeatedly used development clips measured combined rat AP50 **0.9583** with exact PT/ONNX parity. Confidence 0.50 caused six false full-video events on a stationary object; one development-only trial at 0.70 removed them. Root locked the model and 0.70 runtime settings before one evaluation on four whole reserved clips. That reserve measured rat AP50 **0.9258** and person AP50 **0.8764** on 59 reviewed frames. All 20 saved full-video event crops visibly contain the plush. The reserve clips share the same camera, table, session, and nearby capture times with training clips, so this is a weaker generalization check than a newly recorded room. Event counts are repeated firings, not annotated push recall.

The exact V4 ONNX ran on a Raspberry Pi with ARM64 ONNX Runtime 1.22.1 at roughly 56 ms median per saved frame. Positive live-camera accuracy, formal 20-push event recall, and new-room generalization remain unverified. The reviewed labels were made by Codex agents without independent human signoff. Infrared and live-rat performance were not tested.

## Post-lock changed-view supplement

The separate [V4 new-room evaluation supplement](rat-litroom-v4-new-room-evaluation-20260927.zip) preserves three whole recordings captured after the model and confidence 0.70 were locked. It is 93,143,338 bytes, has SHA256 `8e9a126fc1360bae1a19378d46743f96a31a8a361650288b55d1b34b895d7661`, and contains 1,919 files. Extract it and run its `verify_bundle.py` to check all 1,918 listed files; the archive passed root's CRC and checksum checks. The original V4 candidate ZIP above is unchanged.

The supplement's evidence index is:

- `vision/new_room_test/`: three source MP4s, pre-prediction labels and review notes, frozen grayscale test manifest, and source hashes.
- `vision/runs/modal-rat-v4-20260926/new_room_final_once/`: sampled-frame `verification/verification_report.json`, full-video `replay/<clip>/report.json`, event crops, and `audit/independent_review.md`.
- `vision/runs/modal-rat-v4-20260926/pi_live_trial_2026-09-27/`: a plush-free Pi live-viewer timing and event observation, with no API post.

The locked V4 model measured rat AP50 0.8827 on 439 reviewed changed-view frames, below the 0.90 target. Full-video replay saved nine plush events and one black-case false alert in the moving clip, no events for the parked plush, and none in the 181-second people-only clip. These clips are now consumed V5 development material, so they cannot be used as an independent V5 test. The separate V5 candidate above records the adaptation result; the fresh V5 test and its limits are linked above.

The earlier [V2 bundle](rat-litroom-candidate-20260926.zip) remains available for history. Its combined rat AP50 was 0.7903 and it failed the 0.9 box gate. The intervening V3 model passed tuned validation but failed its separate new-scene test; its failure report is preserved inside the V4 archive.
