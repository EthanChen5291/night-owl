# Plush detector candidate bundles

The current recorded-footage candidate is [rat-litroom-v4-candidate-20260927.zip](rat-litroom-v4-candidate-20260927.zip). It contains the locked V4 ONNX and PyTorch model, all reviewed grayscale training/validation frames and labels, source and package lockfile, checkpoint selection and training curves, CPU evaluation reports, original development and reserved videos, truth/provenance, replay crops, and a Raspberry Pi saved-frame timing report. It is a **candidate for a lit metal-table plush demo**, not a promoted detector for live rats.

## Extract and verify

From the repository root:

```sh
unzip vision/artifacts/rat-litroom-v4-candidate-20260927.zip -d /tmp/barn-owl-v4
cd /tmp/barn-owl-v4/rat-litroom-v4-candidate-20260927
python3 verify_bundle.py
```

The ZIP has 2,193 files, is 91,067,802 bytes, and has SHA256 `5dae4e6446a5613fea79ffdec7c4ebcd9ecccad2fadcf67232f77a17d09fae45`. The extracted checksum script verifies all 2,192 other files. Extraction, checksum verification, and the bundled reserved-test source/provenance check passed on a clean temporary directory. The extracted `README.md` gives the exact model hashes, recorded results, and a `--no-post` Pi dry-run command at locked confidence 0.70. Keep the model under a distinct filename; do not replace `pi/rat.onnx` until formal promotion gates pass.

## Evidence and limits

The repeatedly used development clips measured combined rat AP50 **0.9583** with exact PT/ONNX parity. Confidence 0.50 caused six false full-video events on a stationary object; one development-only trial at 0.70 removed them. Root locked the model and 0.70 runtime settings before one evaluation on four whole reserved clips. That reserve measured rat AP50 **0.9258** and person AP50 **0.8764** on 59 reviewed frames. All 20 saved full-video event crops visibly contain the plush. The reserve clips share the same camera, table, session, and nearby capture times with training clips, so this is a weaker generalization check than a newly recorded room. Event counts are repeated firings, not annotated push recall.

The exact V4 ONNX ran on a Raspberry Pi with ARM64 ONNX Runtime 1.22.1 at roughly 56 ms median per saved frame. Live camera operation, formal 20-push event recall, and a three-minute negative reel remain unverified. The reviewed labels were made by Codex agents without independent human signoff. Infrared and live-rat performance were not tested.

The earlier [V2 bundle](rat-litroom-candidate-20260926.zip) remains available for history. Its combined rat AP50 was 0.7903 and it failed the 0.9 box gate. The intervening V3 model passed tuned validation but failed its separate new-scene test; its failure report is preserved inside the V4 archive.
