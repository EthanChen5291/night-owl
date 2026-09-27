"""Relay retry against the actual API handler and event store.

Run with api/.venv/bin/python so FastAPI, h3, and httpx are available.
"""
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "api"))
sys.path.insert(0, str(REPO / "vision" / "pi"))

from event_relay import Relay  # noqa: E402
from main import create_app  # noqa: E402


class Reply:
    def __init__(self, status, body):
        self.status = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit):
        return self.body


class ApiIntegrationTests(unittest.TestCase):
    def test_lost_first_receipt_exact_retry_updates_posterior_once(self):
        body = {"node_id": "demo-01", "h3": "892a100d2c3ffff", "ts": "2026-09-26T21:04:11.302Z",
                "class": "rat", "conf": 0.87, "n_hits": 3,
                "bbox": [0.41, 0.62, 0.18, 0.12], "crop_b64": "anBlZw==", "fw": "0.1.0"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events_file = root / "api-events.jsonl"
            saved = root / "saved"
            saved.mkdir()
            raw = json.dumps(body, indent=1).encode()
            (saved / "event_0001_2026-09-26T210411302Z.json").write_bytes(raw)
            app = create_app(data_dir=REPO, events_file=events_file)
            with TestClient(app) as client:
                calls = []

                def urlopen(request, timeout):
                    self.assertEqual(request.full_url, "http://127.0.0.1:8765/event")
                    self.assertGreater(timeout, 0)
                    calls.append(request.data)
                    response = client.post("/event", content=request.data,
                                           headers={"content-type": "application/json"})
                    self.assertEqual(response.status_code, 200)
                    if len(calls) == 1:
                        raise urllib.error.URLError("receipt lost after API accepted")
                    return Reply(response.status_code, response.content)

                with patch("event_relay.open_no_redirect", side_effect=urlopen):
                    result = Relay(saved, api="http://127.0.0.1:8765", post=True,
                                   settle_seconds=0, retry_delay=0, max_attempts=2).scan_once()[0]
                self.assertEqual(calls, [raw, raw])
                self.assertEqual(result["outcome"], "not_accepted")
                self.assertTrue(result["possible_prior_delivery"])
                self.assertEqual(client.get("/health").json()["events"], 1)
                self.assertEqual(client.get("/queue").json()["events"][0]["crop_b64"], body["crop_b64"])
                self.assertEqual(app.state.store.posteriors[("2026-09", body["h3"])].n_events, 1)
            self.assertEqual(len(events_file.read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
