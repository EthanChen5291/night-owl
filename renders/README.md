# renders — deck renders of the node (SB-01)

`render_node.py` asks Gemini (`gemini-3-pro-image`, via `google-genai`) for product renders of the D3 node, using the OpenSCAD previews in `~/div-hacks-26/enclosure/preview` as references. Needs `GEMINI_API_KEY` in `.env`. Run it as `./renders/render_node.py --shot <name>` (the shebang pulls the deps with `uv`); `--dry-run` prints the request.

Deck shots (`--shot`): `hero` (three-quarter, on a rail), `situ` (on a tree guard at night), `top` (Pi through the clear lid), `variants-sheet` (D1–D6, D3 chosen), `concepts-sheet` (D–H, D chosen), `face-a` / `face-b` / `face-c` (the v2 faceplate styles). Free prompts via `--prompt`, extra refs via `--ref`, several tries via `--n`.

Outputs land in `renders/node/`, which is **gitignored**; the five deck PNGs (`hero.png`, `situ.png`, `top.png`, `variants-sheet.png`, `concepts-sheet.png`) get copied up to `renders/` by hand once picked. The originals live in `~/divMap/renders/node/`, also gitignored, so regenerate rather than hunt.

The cyan band glow in `hero` and `situ` is a demo-only touch for the stage and the deck; a field node is dark.
