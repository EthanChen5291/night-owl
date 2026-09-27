#!/usr/bin/env python3
"""Opt-in relay for crop events saved by live_worker.py.

The worker never waits for this process. By default this command only lists
ready events; --post and an explicit --api are both required to send anything.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

EVENT_KEYS = {"node_id", "h3", "ts", "class", "conf", "n_hits", "bbox", "crop_b64", "fw"}
MAX_EVENT_BYTES = 5_000_000
TERMINAL = {"accepted", "not_accepted", "rejected"}


def api_event_url(base: str) -> str:
    url = urllib.parse.urlsplit(base)
    if ("?" in base or "#" in base or url.scheme not in {"http", "https"} or
            not url.hostname or url.username or url.password or url.query or url.fragment):
        raise ValueError("--api must be an explicit http(s) API base URL without credentials, query, or fragment")
    return base.rstrip("/") + "/event"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def open_no_redirect(request: urllib.request.Request, timeout: float):
    return urllib.request.build_opener(NoRedirect).open(request, timeout=timeout)


class Journal:
    """Durable attempt and receipt records. An attempt precedes every POST."""

    def __init__(self, path: Path, api_url: str):
        self.path = path
        self.api_url = api_url
        self.attempts: dict[tuple[str, str], int] = {}
        self.terminal: dict[tuple[str, str], dict] = {}
        self.hashes_by_name: dict[str, set[str]] = {}
        if path.exists():
            for line_no, line in enumerate(path.read_text().splitlines(), 1):
                try:
                    record = json.loads(line)
                    name, digest = record["file"], record["sha256"]
                    kind = record["kind"]
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValueError(f"invalid relay journal line {line_no}: {exc}") from exc
                if record.get("api_url") != api_url:
                    raise ValueError(f"relay journal API mismatch at line {line_no}: "
                                     f"recorded {record.get('api_url')!r}, requested {api_url!r}; "
                                     "use the original API or a new events directory")
                if not isinstance(name, str) or not isinstance(digest, str):
                    raise ValueError(f"invalid relay journal line {line_no}: file/hash types")
                key = (name, digest)
                self.hashes_by_name.setdefault(name, set()).add(digest)
                if kind == "attempt":
                    self.attempts[key] = max(self.attempts.get(key, 0), int(record["attempt"]))
                elif kind == "receipt" and record.get("outcome") in TERMINAL:
                    self.terminal[key] = record

    def append(self, record: dict) -> None:
        record = {**record, "at_unix": time.time(), "api_url": self.api_url}
        data = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
        new_file = not self.path.exists()
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "ab") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if new_file:
            directory_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        key = (record["file"], record["sha256"])
        self.hashes_by_name.setdefault(key[0], set()).add(key[1])
        if record["kind"] == "attempt":
            self.attempts[key] = max(self.attempts.get(key, 0), record["attempt"])
        elif record["kind"] == "receipt" and record.get("outcome") in TERMINAL:
            self.terminal[key] = record


def ready_event(path: Path, settle_seconds: float) -> tuple[bytes, dict, str] | None:
    """Return a complete stable event, or leave a new/partial file for a later scan."""
    try:
        before = path.stat()
        if time.time() - before.st_mtime < settle_seconds or before.st_size > MAX_EVENT_BYTES:
            return None
        raw = path.read_bytes()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            return None
        body = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(body, dict) or set(body) != EVENT_KEYS:
        return None
    return raw, body, hashlib.sha256(raw).hexdigest()


def send(url: str, raw: bytes, timeout: float) -> dict:
    request = urllib.request.Request(url, data=raw, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "nightowl-event-relay/1"})
    try:
        with open_no_redirect(request, timeout) as response:
            status = response.status
            data = response.read(65_537)
    except urllib.error.HTTPError as exc:
        try:
            return {"outcome": "transient_error" if exc.code in {408, 429} or exc.code >= 500 else "rejected",
                    "http_status": exc.code, "detail": f"HTTP {exc.code}"}
        finally:
            exc.close()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"outcome": "transient_error", "http_status": None, "detail": type(exc).__name__}
    try:
        response = json.loads(data)
    except (ValueError, UnicodeError):
        return {"outcome": "transient_error", "http_status": status, "detail": "invalid JSON response"}
    if len(data) > 65_536 or not isinstance(response, dict) or response.get("ok") is not True or not isinstance(response.get("accepted"), bool):
        return {"outcome": "transient_error", "http_status": status, "detail": "missing ok/accepted response"}
    accepted = response["accepted"]
    return {"outcome": "accepted" if accepted else "not_accepted",
            "http_status": status, "accepted": accepted,
            "detail": "accepted" if accepted else "server declined or duplicate"}


class Relay:
    def __init__(self, events_dir: Path, *, api: str | None = None, post: bool = False,
                 max_attempts: int = 3, timeout: float = 3.0, retry_delay: float = 0.5,
                 settle_seconds: float = 0.5):
        if not events_dir.is_dir():
            raise ValueError(f"missing events directory: {events_dir}")
        if post and not api:
            raise ValueError("--post requires --api")
        if max_attempts < 1 or timeout <= 0 or retry_delay < 0 or settle_seconds < 0:
            raise ValueError("invalid relay timing or retry settings")
        self.events_dir = events_dir
        self.post = post
        self.url = api_event_url(api) if api else None
        self.max_attempts = max_attempts
        self.timeout = timeout
        self.retry_delay = retry_delay
        self.settle_seconds = settle_seconds
        self.journal = Journal(events_dir / "relay_receipts.jsonl", self.url) if post else None
        self.dry_seen: set[tuple[str, str]] = set()
        self.reported_problems: set[tuple[str, str, str]] = set()

    def scan_once(self) -> list[dict]:
        results = []
        for path in sorted(self.events_dir.glob("event_*.json")):
            event = ready_event(path, self.settle_seconds)
            if event is None:
                continue
            raw, body, digest = event
            key = (path.name, digest)
            summary = {"file": path.name, "sha256": digest, "ts": body["ts"],
                       "class": body["class"], "conf": body["conf"], "n_hits": body["n_hits"]}
            if not self.post:
                if key not in self.dry_seen:
                    results.append({**summary, "outcome": "dry_run"})
                    self.dry_seen.add(key)
                continue
            assert self.journal is not None and self.url is not None
            if self.journal.hashes_by_name.get(path.name, {digest}) != {digest}:
                marker = (*key, "changed_after_journal")
                if marker not in self.reported_problems:
                    results.append({**summary, "outcome": "changed_after_journal"})
                    self.reported_problems.add(marker)
                continue
            if key in self.journal.terminal:
                continue
            prior = self.journal.attempts.get(key, 0)
            if prior >= self.max_attempts:
                marker = (*key, "attempts_exhausted")
                if marker not in self.reported_problems:
                    results.append({**summary, "outcome": "attempts_exhausted", "attempts": prior})
                    self.reported_problems.add(marker)
                continue
            for attempt in range(prior + 1, self.max_attempts + 1):
                self.journal.append({"kind": "attempt", "file": path.name, "sha256": digest,
                                     "attempt": attempt})
                receipt = send(self.url, raw, self.timeout)
                record = {"kind": "receipt", "file": path.name, "sha256": digest,
                          "attempt": attempt, "possible_prior_delivery": attempt > 1, **receipt}
                self.journal.append(record)
                if receipt["outcome"] in TERMINAL:
                    results.append({**summary, **record})
                    break
                if attempt == self.max_attempts:
                    results.append({**summary, "outcome": "attempts_exhausted", "attempts": attempt,
                                    "last_error": receipt["detail"]})
                    self.reported_problems.add((*key, "attempts_exhausted"))
                else:
                    time.sleep(self.retry_delay * (2 ** (attempt - 1)))
        return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events-dir", type=Path, required=True)
    parser.add_argument("--api", help="explicit API base URL; required with --post")
    parser.add_argument("--post", action="store_true", help="send events; default is dry run")
    parser.add_argument("--once", action="store_true", help="scan once, then exit")
    parser.add_argument("--poll-seconds", type=float, default=0.5)
    parser.add_argument("--settle-seconds", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=0.5)
    args = parser.parse_args(argv)
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    lock = None
    if args.post:
        if not args.api:
            parser.error("--post requires --api")
        if not args.events_dir.is_dir():
            parser.error(f"missing events directory: {args.events_dir}")
        lock = (args.events_dir / "relay.lock").open("a+")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            parser.error("another relay is already posting from this events directory")
    try:
        relay = Relay(args.events_dir, api=args.api, post=args.post,
                      max_attempts=args.max_attempts, timeout=args.timeout,
                      retry_delay=args.retry_delay, settle_seconds=args.settle_seconds)
    except ValueError as exc:
        if lock:
            lock.close()
        parser.error(str(exc))
    stop = False

    def request_stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        while not stop:
            for result in relay.scan_once():
                print(json.dumps(result, sort_keys=True), flush=True)
            if args.once:
                break
            time.sleep(args.poll_seconds)
    finally:
        if lock:
            lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
