# Barn Owl pitch

Current deck: [v11 PPTX](out/barn-owl-three-minute-pitch-v11.pptx) · [three-minute script](script.md). The V3 independent rat AP50 result on slide 5 missed the .90 target; update this version if later detector work changes the measured result.

The five-slide deck and three-minute speaker script use the current `model/out/backtest.json`, two cells from `model/out/cells.json`, and the independent detector result in `vision/HILL_CLIMB.md`. Slide 3 is a native editable chart. Slide 4 embeds a teammate's actual photo of the physical prototype. `build.mjs` reads the model exports when it builds the deck, so later backtest and cell values can be refreshed without editing chart coordinates. The recorded-footage integration numbers on slide 4 are a 2026-09-26 local replay snapshot and must be edited if that run changes.

To rebuild with the bundled Codex presentation runtime, set `RUNTIME_NODE_MODULES` to its Node package directory, link that directory as `pitch/node_modules`, and run `node pitch/build.mjs` from the repo root. Use a new `DECK_VERSION` for each later finalization. Then update the spoken numbers in `script.md` to match the new chart.

Before presenting, update the formal push and physical Pi test status only after measured results exist. If the audience sees recorded footage or a canned POST, say which one it is.

The [current training demo clip](training-demo.md) uses the actual V3 training log and ONNX predictions on fixed validation footage. Its V2 caption distinguishes tuned validation from the independent test that missed the .90 target. V1 remains a dated pre-test snapshot and should not be shown as the current result.
