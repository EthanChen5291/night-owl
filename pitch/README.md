# Barn Owl pitch

The five-slide deck and three-minute speaker script use the current `model/out/backtest.json` and two cells from `model/out/cells.json`. Slide 3 is a native editable chart. `build.mjs` reads the exported values when it builds the deck, so later model results can be refreshed without editing chart coordinates.

To rebuild with the bundled Codex presentation runtime, set `RUNTIME_NODE_MODULES` to its Node package directory, link that directory as `pitch/node_modules`, and run `node pitch/build.mjs` from the repo root. Use `DECK_VERSION=v6` (or another new version) for each later finalization. Then update the spoken numbers in `script.md` to match the new chart.

Before presenting, replace “held-out rig validation pending” only if clip-held-out and event-level tests have produced measured results. If the live event is canned, say so on stage.
