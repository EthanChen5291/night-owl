# Barn Owl pitch

Current deck: [v16 PPTX](out/barn-owl-three-minute-pitch-v16.pptx) · [three-minute script](script.md). Slide 5 distinguishes V4's failed new-room box test from V5's improved development scores. A fresh independent V5 test and positive live-camera test are pending.

The five-slide deck and three-minute speaker script use the current `model/out/backtest.json`, two cells from `model/out/cells.json`, the [V4 new-room evaluation ZIP](../vision/artifacts/rat-litroom-v4-new-room-evaluation-20260927.zip), and the [V5 development candidate ZIP](../vision/artifacts/rat-litroom-v5-development-candidate-20260927.zip). V5 scores come from `reports/metrics.json` inside that archive. Slide 3 is a native editable chart. Slide 4 embeds a teammate's actual photo of the physical prototype. `build.mjs` reads the model exports when it builds the deck, so later backtest and cell values can be refreshed without editing chart coordinates. The recorded-footage integration numbers on slide 4 are an earlier V2 local replay snapshot, not a V5 API test.

To rebuild with the bundled Codex presentation runtime, set `RUNTIME_NODE_MODULES` to its Node package directory, link that directory as `pitch/node_modules`, and run `node pitch/build.mjs` from the repo root. Use a new `DECK_VERSION` for each later finalization. Then update the spoken numbers in `script.md` to match the new chart.

Before presenting, update the fresh V5 test and positive live-camera status only after measured results exist. The V5 ONNX has already run on a saved positive frame on the physical Pi; this does not verify a live positive trigger. If the audience sees recorded footage or a canned POST, say which one it is.

The [V5 recorded-development montage](v5-montage.md) uses four saved, reviewed replay event stills and ends with the tuned-score and fresh-test limits. It is the current short video for the pitch. The [V4 training demo clip](training-demo.md) is a dated V4 artifact; its closing caption predates V4's failed new-room test and V5 adaptation. Earlier video versions remain available for history.
