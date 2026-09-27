"""The rat sighting tool must keep data-integrity claims tied to fetched evidence."""

import hashlib
import io
import json

import pytest

import agent


JPEG = b"\xff\xd8sighting-test\xff\xd9"
HASH = hashlib.sha256(JPEG).hexdigest()
ANCHOR = "anchored-row-hash"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("unexpected external request")

    monkeypatch.setattr(agent.urllib.request, "urlopen", blocked)


def _row(*, image=True, suffix="1"):
    return {"ts": "2026-09-27T01:15:00Z", "label": "rat", "confidence": 0.91,
            "image_sha256": HASH if image else None,
            "solana": {"id": suffix, "status": "sent", "hash": ANCHOR, "sig": "signature-" + suffix}}


def _verification(*, picture=True, row_hash=ANCHOR, row_ok=True, rpc="https://rpc.example"):
    now = {"ok": row_ok, "hash": row_hash}
    if picture is not ...:
        now["picture"] = {"ok": picture}
    return {"now": now, "rpc": rpc, "address": "node-key", "cluster": "devnet"}


def _transaction(*, meta=None, signer="node-key"):
    if meta is None:
        meta = {"err": None, "logMessages": [f'Program log: Memo (len 29): "owl1 det {ANCHOR}"']}
    return {"result": {"meta": meta, "transaction": {"message": {"accountKeys": [signer]}}, "blockTime": 100}}


class _Response:
    def __init__(self, body):
        self.body = io.BytesIO(json.dumps(body).encode())

    def __enter__(self):
        return self.body

    def __exit__(self, *_):
        self.body.close()


def _rpc(monkeypatch, body=None, error=None):
    def urlopen(_req, timeout):
        assert timeout == 10
        if error:
            raise error
        return _Response(_transaction() if body is None else body)
    monkeypatch.setattr(agent.urllib.request, "urlopen", urlopen)


def _dashboard(monkeypatch, rows, verify=None, image_bytes=JPEG):
    def dash(path):
        if path == "/api/detections":
            return rows
        assert path.startswith("/api/solana?verify=")
        if callable(verify):
            return verify(path)
        return _verification() if verify is None else verify

    def dash_bytes(path):
        assert path.startswith("/api/detections?image=")
        if callable(image_bytes):
            return image_bytes(path)
        return image_bytes

    monkeypatch.setattr(agent, "_dash", dash)
    monkeypatch.setattr(agent, "_dash_bytes", dash_bytes)


def test_matching_download_and_explicit_picture_check_allow_badge(monkeypatch):
    _dashboard(monkeypatch, [_row()])
    _rpc(monkeypatch)
    result, images = agent.t_rat_sightings(None, {})
    sol = result["sightings"][0]["solana"]
    assert sol["verified"] is True
    assert sol["row_only_verified"] is False
    assert sol["image_bytes_match"] is True
    assert sol["chain_status"] == "verified"
    assert "data integrity verified on Solana" in images[0]["caption"]


def test_mismatched_download_is_not_shown_or_verified(monkeypatch):
    _dashboard(monkeypatch, [_row()], image_bytes=b"different JPEG")
    _rpc(monkeypatch)
    result, images = agent.t_rat_sightings(None, {})
    sighting = result["sightings"][0]
    assert sighting["image_status"] == "hash_mismatch"
    assert sighting["solana"]["image_bytes_match"] is False
    assert sighting["solana"]["verified"] is False
    assert sighting["solana"]["verification_status"] == "failed"
    assert images == []


@pytest.mark.parametrize("picture", [..., None, 1, "true", False])
def test_missing_or_non_true_picture_check_cannot_verify(monkeypatch, picture):
    _dashboard(monkeypatch, [_row()], verify=_verification(picture=picture))
    _rpc(monkeypatch)
    result, images = agent.t_rat_sightings(None, {})
    sol = result["sightings"][0]["solana"]
    assert sol["verified"] is False
    assert sol["picture_status"] != "verified"
    assert "verified" not in images[0]["caption"]


def test_historical_row_has_distinct_row_only_result(monkeypatch):
    _dashboard(monkeypatch, [_row(image=False)], verify=_verification(picture=...))
    _rpc(monkeypatch)
    result, images = agent.t_rat_sightings(None, {})
    sol = result["sightings"][0]["solana"]
    assert sol["row_only_verified"] is True
    assert sol["verified"] is False
    assert sol["verification_status"] == "row_only_verified"
    assert "picture_unchanged" not in sol
    assert images == []


@pytest.mark.parametrize("meta", [{"err": {"InstructionError": [0, "Custom"]}, "logMessages": [f'Memo (len 29): "owl1 det {ANCHOR}"']},
                                         {}, None])
def test_failed_or_missing_transaction_meta_cannot_anchor(monkeypatch, meta):
    _dashboard(monkeypatch, [_row()])
    body = _transaction(meta=meta) if meta is not None else _transaction()
    if meta is None:
        del body["result"]["meta"]
    _rpc(monkeypatch, body)
    result, _ = agent.t_rat_sightings(None, {})
    sol = result["sightings"][0]["solana"]
    assert sol["verified"] is False
    assert sol["chain_status"] == ("failed" if meta and meta.get("err") else "unavailable")
    assert sol["on_chain"] is (False if meta and meta.get("err") else None)
    assert "anchored_at" not in sol


def test_rpc_error_is_unavailable_and_keeps_detection(monkeypatch):
    _dashboard(monkeypatch, [_row()])
    _rpc(monkeypatch, error=OSError("RPC offline"))
    result, images = agent.t_rat_sightings(None, {})
    sol = result["sightings"][0]["solana"]
    assert result["total_in_window"] == 1
    assert sol["chain_status"] == "unavailable"
    assert sol["verification_status"] == "unavailable"
    assert sol["on_chain"] is None
    assert "verified" not in images[0]["caption"]


def test_rpc_missing_transaction_is_unavailable(monkeypatch):
    _dashboard(monkeypatch, [_row()])
    _rpc(monkeypatch, {"result": None})
    result, _ = agent.t_rat_sightings(None, {})
    sol = result["sightings"][0]["solana"]
    assert sol["chain_status"] == "unavailable"
    assert sol["on_chain"] is None
    assert sol["verified"] is False


def test_unsent_transaction_is_pending(monkeypatch):
    row = _row()
    del row["solana"]["sig"]
    _dashboard(monkeypatch, [row])
    result, images = agent.t_rat_sightings(None, {})
    sol = result["sightings"][0]["solana"]
    assert sol["chain_status"] == "pending"
    assert sol["on_chain"] is None
    assert sol["verified"] is False
    assert "verified" not in images[0]["caption"]


def test_missing_first_image_keeps_both_rows_and_shows_second(monkeypatch):
    def image(path):
        if "missing" in path:
            raise FileNotFoundError("image unavailable")
        return JPEG

    first = _row(suffix="1")
    first["image_sha256"] = "missing"
    _dashboard(monkeypatch, [first, _row(suffix="2")], image_bytes=image)
    _rpc(monkeypatch)
    result, images = agent.t_rat_sightings(None, {})
    assert len(result["sightings"]) == 2
    assert result["sightings"][0]["image_status"] == "unavailable"
    assert result["sightings"][0]["solana"]["verified"] is False
    assert result["sightings"][1]["image_status"] == "available"
    assert result["sightings"][1]["solana"]["verified"] is True
    assert len(images) == 1


def test_image_download_attempts_stop_at_three(monkeypatch):
    attempts = []

    def missing(path):
        attempts.append(path)
        raise FileNotFoundError("image unavailable")

    _dashboard(monkeypatch, [_row(suffix=str(i)) for i in range(8)], image_bytes=missing)
    _rpc(monkeypatch)
    result, images = agent.t_rat_sightings(None, {"limit": 8})
    assert len(result["sightings"]) == 8
    assert len(attempts) == 3
    assert [s["image_status"] for s in result["sightings"]] == ["unavailable"] * 3 + ["not_requested"] * 5
    assert result["sightings"][3]["solana"]["verification_status"] == "not_checked"
    assert result["sightings"][3]["solana"]["verified"] is False
    assert images == []


def test_failed_first_verification_keeps_second_row(monkeypatch):
    def verify(path):
        if path.endswith("1"):
            raise OSError("dashboard verifier offline")
        return _verification()

    _dashboard(monkeypatch, [_row(suffix="1"), _row(suffix="2")], verify=verify)
    _rpc(monkeypatch)
    result, images = agent.t_rat_sightings(None, {})
    first, second = result["sightings"]
    assert first["solana"]["verification_status"] == "unavailable"
    assert "dashboard verifier offline" in first["solana"]["verification_error"]
    assert first["solana"]["verified"] is False
    assert second["solana"]["verified"] is True
    assert len(images) == 2
    assert "verified" not in images[0]["caption"]
    assert "verified" in images[1]["caption"]


def test_verify_false_never_applies_badge(monkeypatch):
    _dashboard(monkeypatch, [_row()])
    result, images = agent.t_rat_sightings(None, {"verify": False})
    assert result["sightings"][0]["solana"]["verification_status"] == "not_checked"
    assert result["sightings"][0]["solana"]["verified"] is False
    assert result["sightings"][0]["image_status"] == "available"
    assert "verified" not in images[0]["caption"]


def test_with_images_false_does_not_claim_downloaded_bytes_verified(monkeypatch):
    def should_not_download(_path):
        raise AssertionError("image download should be disabled")

    _dashboard(monkeypatch, [_row()], image_bytes=should_not_download)
    _rpc(monkeypatch)
    result, images = agent.t_rat_sightings(None, {"with_images": False})
    sol = result["sightings"][0]["solana"]
    assert sol["picture_unchanged"] is True
    assert sol["image_bytes_match"] is None
    assert sol["verified"] is False
    assert sol["verification_status"] == "unavailable"
    assert result["sightings"][0]["image_status"] == "not_requested"
    assert images == []


@pytest.mark.parametrize("verification,chain_status", [(_verification(row_hash="other"), "verified"),
                                                      (_verification(), "mismatch")])
def test_row_hash_or_signer_mismatch_cannot_verify(monkeypatch, verification, chain_status):
    _dashboard(monkeypatch, [_row()], verify=verification)
    _rpc(monkeypatch, _transaction(signer="other-key" if chain_status == "mismatch" else "node-key"))
    result, images = agent.t_rat_sightings(None, {})
    sol = result["sightings"][0]["solana"]
    assert sol["chain_status"] == chain_status
    assert sol["verified"] is False
    assert "verified" not in images[0]["caption"]


@pytest.mark.parametrize("signer,address,logs", [(None, None, [f'Memo (len 29): "owl1 det {ANCHOR}"']),
                                               ("", "", [f'Memo (len 29): "owl1 det {ANCHOR}"']),
                                               ("node-key", None, [f'Memo (len 29): "owl1 det {ANCHOR}"']),
                                               ("node-key", "node-key", None)])
def test_missing_signer_address_or_logs_are_unavailable(monkeypatch, signer, address, logs):
    verification = _verification()
    verification["address"] = address
    _dashboard(monkeypatch, [_row()], verify=verification)
    _rpc(monkeypatch, _transaction(meta={"err": None, "logMessages": logs}, signer=signer))
    result, images = agent.t_rat_sightings(None, {})
    sol = result["sightings"][0]["solana"]
    assert sol["chain_status"] == "unavailable"
    assert sol["on_chain"] is None
    assert sol["verified"] is False
    assert "verified" not in images[0]["caption"]
