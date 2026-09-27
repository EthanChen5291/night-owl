# Grok assistant branch: integration review

Reviewed `origin/grok-agent` at `3e51f46298f748e39ad2473de0f13a2887e62e64` against frontend `57d69c4`. Their merge base is `575cf4899a361f2f41ca9992aab0030b3e2fc238` (`main`). The three Grok-only commits are `1063172` (map assistant and Photon iMessage), `ec8a13d` (map controls), and `3e51f46` (hover-only button). None is in the frontend branch. This was a read-only source and merge-tree review; no agent, messaging service, or outbound call was run. Keep the branch unmerged for the current demo.

Before integration, fix two consistency gaps in `api/agent.py`:

1. `t_node_sites()` at line 260 reads `model/out/plan.json` directly (line 261). The live map uses `Store.plan(month, k)`, which re-ranks after accepted detections. The assistant would still describe the old rank after the observed live event moved the demo cell from rank 2 to rank 1. Use the same store plan and selected month as the map.
2. `Data.cells()` at line 144 calls `Store.cells(None)` (line 145). The frontend can show a selected historical month, so assistant scores can refer to a different month. Pass the selected month through the chat request and every cell/plan lookup, and report the source month returned by the store.

The branch adds `mount_agent()` to `api/main.py` (line 167), plus a web chat panel and `imessage/` service. A read-only merge-tree simulation found one textual conflict in `web/src/index.css` where the current mobile layout and assistant CSS both extend the same tail section. `api/main.py`, `web/src/App.tsx`, and scene changes merge textually but need an integrated build and behavior check. The assistant route returns 503 without `XAI_API_KEY`; Photon also needs project credentials and a running iMessage process. These commits alone provide no evidence that either service was configured or deployed.

`t_camera_image()` at `api/agent.py:329` calls dashboard `/api/state?live=1` (lines 332–337), which can wake the Pi camera. Treat that as an explicit camera action. If `/agent/chat` is exposed publicly with the server's XAI and dashboard tokens, add caller authorization before enabling it: the current route checks the server key and per-IP rate but no caller identity (`api/agent.py:600–605`).
