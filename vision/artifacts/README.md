# Plush detector candidate bundles

The current recorded-footage candidate is [rat-litroom-v4-candidate-20260927.zip](rat-litroom-v4-candidate-20260927.zip). It contains the locked V4 ONNX and PyTorch model, all reviewed grayscale training/validation frames and labels, source and package lockfile, checkpoint selection and training curves, CPU evaluation reports, original development and reserved videos, truth/provenance, replay crops, and a Raspberry Pi saved-frame timing report. It is a **candidate for a lit metal-table plush demo**, not a promoted detector for live rats.

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

The locked model measured rat AP50 0.8827 on 439 reviewed changed-view frames, below the 0.90 target. Full-video replay saved nine plush events and one black-case false alert in the moving clip, no events for the parked plush, and none in the 181-second people-only clip. These clips are now consumed V5 development material, so they cannot be used as an independent V5 test. V5 training results are pending.

The earlier [V2 bundle](rat-litroom-candidate-20260926.zip) remains available for history. Its combined rat AP50 was 0.7903 and it failed the 0.9 box gate. The intervening V3 model passed tuned validation but failed its separate new-scene test; its failure report is preserved inside the V4 archive.
