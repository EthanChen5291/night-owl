# Night Owl pitch

The current deck is [V20](out/night-owl-three-minute-pitch-v20.pptx), with a [three-minute script](script.md). The project was previously called Barn Owl. Earlier decks and videos keep their original names.

Slide 4 shows one verified event from a live physical Pi camera to the local API and map. During 89.859 seconds of room-lit plush footage, V5 processed 1,346 frames and saved six event crops. Reviewers saw the plush in each crop. The team sent one event; the API accepted it. The map changed from one sighting to two, moved the site from rank 2 to 1, and raised its served score from .1297 to .1618. See the [map screenshot](assets/live-pi-map-20260927.png), [API receipt](evidence/v5-live-integration-result.json), and [Pi run stats](evidence/v5-live-run-stats.json).

One successful event does not establish detector reliability. The [fixed formal event test](../vision/V5_FORMAL_EVENT_RESULTS.md) found alerts on 18 of 19 reviewed plush appearances, but 17 false alerts on a cap and shoe during 190.409 seconds without a plush. It failed the false-alert limit. V5's separate fresh box test did not establish the .90 rat AP50 target. Its as-run score was .615779 on 369 frames; [source review](../vision/V5_FRESH_RESULTS.md) found faulty reference boxes, and no corrected score exists. V6 added hard negatives and trained for 30 epochs, but [preset development checks](evidence/v6-checkpoint-selection.json) failed. The team did not replay V6 or put it on the Pi. V5 remains the demo detector. None of this validates IR footage, wild rats, or field performance.

The deck reads [backtest data](../model/out/backtest.json) and [cell scores](../model/out/cells.json) when it builds. Slide 3 is an editable PowerPoint chart. The 19.5% versus 15.2% result compares monthly active-sign shares of inspected lots in the top 50 cells **that were swept**. It does not count rats citywide or measure a deployment effect.

To rebuild, use the bundled Codex presentation runtime: set `RUNTIME_NODE_MODULES` to its Node package directory, link it as `pitch/node_modules`, and run `node pitch/build.mjs` from the repository root. Set a new `DECK_VERSION` for a later edition, then check the rendered slides and the spoken numbers.

The [V5 development montage](v5-montage.md) and [V4 training clip](training-demo.md) are dated. Their closing captions predate fresh testing. If shown, explain the later failed event test and fresh box-test limit.
