# Plush detector candidate bundle

Download [rat-litroom-candidate-20260926.zip](rat-litroom-candidate-20260926.zip), or pull this branch to get it with the code. This is the room-lit plush detector candidate for the hackathon.

The bundle includes ONNX and PyTorch weights, the reviewed training dataset, evaluation reports, Pi runtime scripts, and recorded-demo evidence. It does not include source videos or offline Pi dependency wheels.

## Extract and verify

From the repository root:

```sh
unzip vision/artifacts/rat-litroom-candidate-20260926.zip -d /tmp/barn-owl-candidate
cd /tmp/barn-owl-candidate/rat-litroom-candidate-20260926
shasum -a 256 -c SHA256SUMS
```

Follow the extracted `README.md` for the Pi copy and room-lit test commands. Use the Pi's reachable address in place of the example address. Keep the candidate filename separate from a promoted model.

Archive SHA256: `69f3cbbea58d3516cbe7d7859c609665cd1e6df042f16cd701d2ed4edd05e411`.

## Validation status

Recorded footage successfully passed through the detector, local API, and frontend. Rat AP50 was 0.9367 on the close-view holdout and 0.7903 across both holdouts. The overall 0.9 gate is not met. Physical Pi timing, the 20-push test, and the three-minute negative test remain pending. This candidate is not validated for live rats or dark IR operation.
