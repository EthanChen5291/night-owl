# Barn Owl pitch

Current deck: [v13 PPTX](out/barn-owl-three-minute-pitch-v13.pptx) · [three-minute script](script.md). Slide 5 reports locked V4 rat AP50 on 59 reserved frames from adjacent clips in the same capture session. A new-room and live-camera test are still pending.

The five-slide deck and three-minute speaker script use the current `model/out/backtest.json`, two cells from `model/out/cells.json`, and V4's locked reserved-test report. Slide 3 is a native editable chart. Slide 4 embeds a teammate's actual photo of the physical prototype. `build.mjs` reads the model exports when it builds the deck, so later backtest and cell values can be refreshed without editing chart coordinates. The recorded-footage integration numbers on slide 4 are an earlier V2 local replay snapshot, not a V4 API test.

To rebuild with the bundled Codex presentation runtime, set `RUNTIME_NODE_MODULES` to its Node package directory, link that directory as `pitch/node_modules`, and run `node pitch/build.mjs` from the repo root. Use a new `DECK_VERSION` for each later finalization. Then update the spoken numbers in `script.md` to match the new chart.

Before presenting, update the formal push and physical Pi test status only after measured results exist. If the audience sees recorded footage or a canned POST, say which one it is.

The [current training demo clip](training-demo.md) uses the actual V4 training log and ONNX predictions on fixed validation footage. Its V3 caption distinguishes tuned validation from the weaker same-session reserved test. Earlier video versions remain dated snapshots and should not be shown as the current result.
