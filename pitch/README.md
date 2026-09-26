# Barn Owl pitch

The five-slide deck and three-minute speaker script use the current `model/out/backtest.json`, two cells from `model/out/cells.json`, and the detector results in `vision/TRAINING_RESULTS.md`. Slide 3 is a native editable chart. `build.mjs` reads the model exports when it builds the deck, so later backtest and cell values can be refreshed without editing chart coordinates. The recorded-footage integration numbers on slide 4 are a 2026-09-26 local replay snapshot and must be edited if that run changes.

To rebuild with the bundled Codex presentation runtime, set `RUNTIME_NODE_MODULES` to its Node package directory, link that directory as `pitch/node_modules`, and run `node pitch/build.mjs` from the repo root. Use `DECK_VERSION=v9` (or another new version) for each later finalization. Then update the spoken numbers in `script.md` to match the new chart.

Before presenting, update the formal push and physical Pi test status only after measured results exist. If the audience sees recorded footage or a canned POST, say which one it is.
