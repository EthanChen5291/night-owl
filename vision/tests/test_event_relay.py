import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PI = Path(__file__).resolve().parents[1] / "pi"
sys.path.insert(0, str(PI))

from event_relay import Journal, Relay, api_event_url  # noqa: E402


BODY = {"node_id": "demo-01", "h3": "892a100d2c3ffff", "ts": "2026-09-26T21:04:11.302Z",
        "class": "rat", "conf": 0.87, "n_hits": 3, "bbox": [0.41, 0.62, 0.18, 0.12],
        "crop_b64": "anBlZw==", "fw": "0.1.0"}


def write_event(directory: Path, raw: bytes | None = None) -> tuple[Path, bytes]:
    path = directory / "event_0001_2026-09-26T210411302Z.json"
    raw = raw if raw is not None else json.dumps(BODY, indent=1).encode()
    path.write_bytes(raw)
    return path, raw


class Endpoint:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.redirect_target_requests = []
        endpoint = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                if self.path != "/event":
                    endpoint.redirect_target_requests.append(("POST", self.path, body))
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"ok":true,"accepted":true}')
                    return
                endpoint.requests.append((self.path, body))
                status, response = endpoint.responses.pop(0)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                if 300 <= status < 400:
                    self.send_header("Location", "/redirect-target")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())

            def do_GET(self):
                endpoint.redirect_target_requests.append(("GET", self.path, b""))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true,"accepted":true}')

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.thread.join(2)
        self.server.server_close()

    @property
    def api(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"


class EventRelayTests(unittest.TestCase):
    def test_default_dry_run_ignores_config_and_does_not_create_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_event(directory)
            (directory / "run_config.json").write_text(json.dumps(BODY))
            (directory / "run_stats.json").write_text(json.dumps(BODY))
            results = Relay(directory, settle_seconds=0).scan_once()
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["outcome"], "dry_run")
            self.assertFalse((directory / "relay_receipts.jsonl").exists())
            relay = Relay(directory, settle_seconds=0)
            self.assertEqual(len(relay.scan_once()), 1)
            self.assertEqual(relay.scan_once(), [])

    def test_post_requires_explicit_api_and_client_error_is_terminal(self):
        with tempfile.TemporaryDirectory() as tmp, Endpoint([(400, {"ok": False})]) as endpoint:
            directory = Path(tmp)
            write_event(directory)
            with self.assertRaisesRegex(ValueError, "requires --api"):
                Relay(directory, post=True)
            relay = Relay(directory, api=endpoint.api, post=True, settle_seconds=0)
            self.assertEqual(relay.scan_once()[0]["outcome"], "rejected")
            self.assertEqual(relay.scan_once(), [])
            self.assertEqual(len(endpoint.requests), 1)

    def test_api_url_rejects_even_empty_literal_query_and_fragment(self):
        for url in ("http://127.0.0.1:8000?", "http://127.0.0.1:8000#",
                    "http://127.0.0.1:8000/api?", "http://127.0.0.1:8000/api#"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "query, or fragment"):
                api_event_url(url)
        self.assertEqual(api_event_url("http://127.0.0.1:8000/api/"),
                         "http://127.0.0.1:8000/api/event")

    def test_post_redirects_are_terminal_and_never_followed(self):
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp, \
                 Endpoint([(status, {})]) as endpoint:
                directory = Path(tmp)
                write_event(directory)
                relay = Relay(directory, api=endpoint.api, post=True, settle_seconds=0,
                              retry_delay=0)
                result = relay.scan_once()[0]
                self.assertEqual(result["outcome"], "rejected")
                self.assertEqual(result["http_status"], status)
                self.assertEqual(len(endpoint.requests), 1)
                self.assertEqual(endpoint.redirect_target_requests, [])
                self.assertEqual(relay.scan_once(), [])

    def test_exact_body_accepted_and_restart_does_not_replay(self):
        with tempfile.TemporaryDirectory() as tmp, Endpoint([(200, {"ok": True, "accepted": True})]) as endpoint:
            directory = Path(tmp)
            _, raw = write_event(directory)
            relay = Relay(directory, api=endpoint.api, post=True, settle_seconds=0)
            first = relay.scan_once()
            self.assertEqual(first[0]["outcome"], "accepted")
            self.assertEqual(endpoint.requests, [("/event", raw)])
            self.assertEqual(Relay(directory, api=endpoint.api, post=True, settle_seconds=0).scan_once(), [])
            records = [json.loads(line) for line in (directory / "relay_receipts.jsonl").read_text().splitlines()]
            self.assertEqual([r["kind"] for r in records], ["attempt", "receipt"])
            self.assertTrue(records[1]["accepted"])

    def test_transient_retry_then_server_declines_is_terminal(self):
        responses = [(503, {"ok": False}), (200, {"ok": True, "accepted": False})]
        with tempfile.TemporaryDirectory() as tmp, Endpoint(responses) as endpoint:
            directory = Path(tmp)
            _, raw = write_event(directory)
            result = Relay(directory, api=endpoint.api, post=True, settle_seconds=0,
                           retry_delay=0).scan_once()[0]
            self.assertEqual(result["outcome"], "not_accepted")
            self.assertFalse(result["accepted"])
            self.assertEqual(endpoint.requests, [("/event", raw), ("/event", raw)])
            self.assertEqual(Relay(directory, api=endpoint.api, post=True, settle_seconds=0).scan_once(), [])
            records = [json.loads(line) for line in (directory / "relay_receipts.jsonl").read_text().splitlines()]
            self.assertEqual([r["outcome"] for r in records if r["kind"] == "receipt"],
                             ["transient_error", "not_accepted"])

    def test_http_408_retries_within_attempt_budget(self):
        with tempfile.TemporaryDirectory() as tmp, Endpoint([
            (408, {"ok": False}), (200, {"ok": True, "accepted": True})
        ]) as endpoint:
            directory = Path(tmp)
            write_event(directory)
            result = Relay(directory, api=endpoint.api, post=True, settle_seconds=0,
                           retry_delay=0, max_attempts=2).scan_once()[0]
            self.assertEqual(result["outcome"], "accepted")
            self.assertEqual(result["attempt"], 2)
            self.assertEqual(len(endpoint.requests), 2)

    def test_receipts_reject_changed_api_destination(self):
        with tempfile.TemporaryDirectory() as tmp, \
             Endpoint([(200, {"ok": True, "accepted": True})]) as first, \
             Endpoint([(200, {"ok": True, "accepted": True})]) as second:
            directory = Path(tmp)
            write_event(directory)
            Relay(directory, api=first.api, post=True, settle_seconds=0).scan_once()
            with self.assertRaisesRegex(ValueError, "relay journal API mismatch"):
                Relay(directory, api=second.api, post=True, settle_seconds=0)
            self.assertEqual(len(first.requests), 1)
            self.assertEqual(second.requests, [])
            records = [json.loads(line) for line in (directory / "relay_receipts.jsonl").read_text().splitlines()]
            self.assertEqual({r["api_url"] for r in records}, {first.api + "/event"})

    def test_attempt_budget_persists_across_restart_and_can_be_raised_explicitly(self):
        responses = [(503, {}), (503, {}), (200, {"ok": True, "accepted": True})]
        with tempfile.TemporaryDirectory() as tmp, Endpoint(responses) as endpoint:
            directory = Path(tmp)
            write_event(directory)
            result = Relay(directory, api=endpoint.api, post=True, settle_seconds=0,
                           retry_delay=0, max_attempts=2).scan_once()[0]
            self.assertEqual(result["outcome"], "attempts_exhausted")
            self.assertEqual(len(endpoint.requests), 2)
            restarted = Relay(directory, api=endpoint.api, post=True, settle_seconds=0,
                              retry_delay=0, max_attempts=2)
            result = restarted.scan_once()[0]
            self.assertEqual(result["outcome"], "attempts_exhausted")
            self.assertEqual(restarted.scan_once(), [])
            self.assertEqual(len(endpoint.requests), 2)
            result = Relay(directory, api=endpoint.api, post=True, settle_seconds=0,
                           retry_delay=0, max_attempts=3).scan_once()[0]
            self.assertEqual(result["outcome"], "accepted")
            self.assertEqual(len(endpoint.requests), 3)

    def test_partial_file_is_waited_for_and_never_posted(self):
        with tempfile.TemporaryDirectory() as tmp, Endpoint([(200, {"ok": True, "accepted": True})]) as endpoint:
            directory = Path(tmp)
            path, _ = write_event(directory, b'{"node_id":"demo-01",')
            relay = Relay(directory, api=endpoint.api, post=True, settle_seconds=0)
            self.assertEqual(relay.scan_once(), [])
            self.assertEqual(endpoint.requests, [])
            path.write_text(json.dumps(BODY))
            self.assertEqual(relay.scan_once()[0]["outcome"], "accepted")
            self.assertEqual(len(endpoint.requests), 1)

    def test_unknown_result_after_attempt_preserves_duplicate_ambiguity(self):
        with tempfile.TemporaryDirectory() as tmp, Endpoint([(200, {"ok": True, "accepted": False})]) as endpoint:
            directory = Path(tmp)
            path, raw = write_event(directory)
            import hashlib
            digest = hashlib.sha256(raw).hexdigest()
            Journal(directory / "relay_receipts.jsonl", endpoint.api + "/event").append(
                {"kind": "attempt", "file": path.name, "sha256": digest, "attempt": 1})
            result = Relay(directory, api=endpoint.api, post=True, settle_seconds=0,
                           retry_delay=0).scan_once()[0]
            self.assertEqual(result["outcome"], "not_accepted")
            self.assertTrue(result["possible_prior_delivery"])
            self.assertEqual(len(endpoint.requests), 1)

    def test_mutated_delivered_file_is_not_posted_again(self):
        with tempfile.TemporaryDirectory() as tmp, Endpoint([(200, {"ok": True, "accepted": True})]) as endpoint:
            directory = Path(tmp)
            path, _ = write_event(directory)
            Relay(directory, api=endpoint.api, post=True, settle_seconds=0).scan_once()
            changed = dict(BODY, conf=0.88)
            path.write_text(json.dumps(changed))
            restarted = Relay(directory, api=endpoint.api, post=True, settle_seconds=0)
            result = restarted.scan_once()[0]
            self.assertEqual(result["outcome"], "changed_after_journal")
            self.assertEqual(restarted.scan_once(), [])
            self.assertEqual(len(endpoint.requests), 1)


if __name__ == "__main__":
    unittest.main()
