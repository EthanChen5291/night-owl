# imessage: Barn Owl over iMessage (Photon Spectrum)

Text the Barn Owl line and the same Grok assistant as the web app's chat answers: rat risk and silent blocks
for any address or neighbourhood, suggested owl sites, the backtest, and the team's Pi (status, motion from
Tiger Data, recordings) with camera frames sent back as photos. The map tools stay in the web app.

`src/index.ts` forwards each text to `POST https://barn-owl.tech/api/agent/chat` (`api/agent.py`) with
`channel: "imessage"` and keeps each conversation's history in memory. Text `reset` to start over.

## Run

```sh
npm install
npm start            # leave it running
```

`.env` (gitignored, written by `npm create spectrum-project`) holds `PROJECT_ID` / `PROJECT_SECRET` from the
[Photon dashboard](https://app.photon.codes). Optional: `BARN_OWL_AGENT_URL` to point at another API
(e.g. `http://localhost:8000/agent/chat` with `api/run.sh`).

Photon needs a phone number on your account before it can enrol you on the line (avatar menu, top right of the
dashboard). Then text the project's line from that phone.

SDK reference: `.agents/skills/spectrum/` and https://photon.codes/docs/spectrum-ts
