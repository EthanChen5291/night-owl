# V5 recorded-development montage

[14.4-second MP4](out/barn-owl-v5-development-replay-montage-v1.mp4) · [preview](out/barn-owl-v5-development-replay-montage-v1-preview.jpg)

The four stills are exact copies of `event_0001_full_crop.jpg` audit images from V5 ONNX replays at fixed confidence 0.70: `new_room_014327` (moving plush), `new_room_014605` (parked plush), `zoom15_b` (old metal table), and `table_c` (old floor). The portable copies are in [`assets/v5-event-stills/`](assets/v5-event-stills/); their originals are also inside the [V5 development candidate ZIP](../vision/artifacts/rat-litroom-v5-development-candidate-20260927.zip) at `reports/dev_replay/<clip>/audit_sheets/event_0001_full_crop.jpg`. Each image shows its actual frame, predicted box, crop, timestamp, and confidence. The original event images were visually reviewed as plush events. `make_v5_montage.py` only lays out and encodes those saved images; it does not run inference or depict live video.

The end card uses `reports/metrics.json` inside the V5 ZIP: selected ONNX rat AP50 0.960806 on the weakest selected development clip and 0.975279 over 146 combined development frames. The prior V4 new-room test scored 0.882675 on 439 reviewed frames, below the 0.90 target. V5 used those V4 test clips for tuning, so its independent fresh test is pending. AP50 is a box-ranking metric, not accuracy or push-event recall. There is no positive live-camera, IR, wild-rat, or field-deployment claim in the video.

Source JPEG SHA-256 values, in montage order: `936f7667ceddf63d1b692aece0ab676ca8b9ebd6636e3c3484e4b7477f120891`, `dc123e128df173deb8e6057518e0e9e40dd28df0026762fe77e025b98f6829fb`, `1b5237be514d18ff71b2a8aed271d7b6a5dccfd5cffadc54bad4b694e77c2bf9`, `7bdf11892061c86d749ef023e8c6efdea52ccab37ea719c7b05d47a13cce0ce4`. Final MP4 SHA-256: `6920bad09ea578296ae1cbee36c4b206b71558d82fb7872566bccfde9d3c48f6`.

To regenerate in this checkout, run `python3 pitch/make_v5_montage.py` with Pillow and `ffmpeg` installed. The Codex bundled Python includes Pillow. The MP4 is ignored by the repository's `*.mp4` rule and must be explicitly added if this version is chosen for delivery.
