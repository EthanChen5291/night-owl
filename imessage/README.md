# NightOwl over iMessage

The Spectrum bot sends text to the NightOwl API. The API stores one chat thread per Spectrum space in SQLite, so a bot restart keeps the conversation. Text `reset`, `new chat`, or `start over` to create a new stored thread. The bot confirms the reset only after the API accepts it.

## Configuration

Set `PROJECT_ID` and `PROJECT_SECRET` for Spectrum, plus `NIGHT_OWL_CHAT_BOT_TOKEN` for the API. The API must have the exact same token. Keep these values in the process environment or the ignored local `.env`; do not commit them.

The bot calls `http://127.0.0.1:8772/agent/chat` by default. Verify the API's listening port before starting it. If the API listens elsewhere, set `NIGHT_OWL_AGENT_URL` to the full chat endpoint, such as `http://127.0.0.1:8000/agent/chat`. Existing `BARN_OWL_AGENT_URL` settings remain a fallback when `NIGHT_OWL_AGENT_URL` is unset. A URL outside loopback must use HTTPS, for example `https://example.org/api/agent/chat`. The bot derives the reset endpoint at the same base path, `/agent/imessage/reset`.

Set `NIGHT_OWL_CHAT_DB` on the API to a persistent, writable path outside the checkout, such as `/var/lib/poc/chat.db`. Keep the database and its SQLite `-wal` and `-shm` files in persistent storage. See [API chat deployment](../api/README.md#agent-chat-and-imessage-deployment).

## Run

With dependencies already installed:

```sh
pnpm test
pnpm typecheck
pnpm start
```

`pnpm start` connects to Spectrum and begins handling real messages. The tests use mocked HTTP calls and do not start the bot. Photon needs a phone number on the account before it can enroll a line. SDK reference: [Spectrum](https://photon.codes/docs/spectrum-ts).
