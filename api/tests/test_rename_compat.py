"""Check configuration precedence without starting services or Pi hardware."""
import ast
import os
from pathlib import Path

import pytest

from store import Store

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("file,name,suffix,default,legacy,current", [
    ("api/store.py", "RING_SIZE", "RING", 2000, "123", "456"),
    ("api/posterior.py", "N0", "N0", 10., "7", "12"),
    ("api/posterior.py", "PRIOR_SCORE_B", "PRIOR_SCORE_B", .2, ".3", ".4"),
    ("api/posterior.py", "MIN_CONF", "MIN_CONF", .5, ".7", ".8"),
    ("api/posterior.py", "MIN_HITS", "MIN_HITS", 3, "4", "5"),
    ("api/agent.py", "DASH", "DASH_URL", "http://127.0.0.1:8771", "http://legacy/", "http://current/"),
    ("vision/pi/detect.py", "API_URL", "API", "http://192.168.7.1:8000", "http://legacy", "http://current"),
])
def test_configuration_uses_current_then_legacy_then_default(monkeypatch, file, name, suffix, default, legacy, current):
    # Execute the real config assignment in isolation. Importing detect would initialize hardware libraries.
    tree = ast.parse((ROOT / file).read_text())
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))
    code = compile(ast.Module(body=[assignment], type_ignores=[]), file, "exec")

    def value():
        namespace = {"os": os}
        exec(code, namespace)
        return namespace[name]

    monkeypatch.delenv(f"NIGHT_OWL_{suffix}", raising=False)
    monkeypatch.delenv(f"BARN_OWL_{suffix}", raising=False)
    assert value() == default
    monkeypatch.setenv(f"BARN_OWL_{suffix}", legacy)
    assert value() == (type(default)(legacy) if not isinstance(default, str) else legacy.rstrip("/"))
    monkeypatch.setenv(f"NIGHT_OWL_{suffix}", current)
    assert value() == (type(default)(current) if not isinstance(default, str) else current.rstrip("/"))


def test_store_paths_keep_legacy_configuration_and_explicit_arguments_win(monkeypatch, tmp_path):
    for suffix in ("DATA_DIR", "EVENTS_FILE"):
        monkeypatch.delenv(f"NIGHT_OWL_{suffix}", raising=False)
        monkeypatch.setenv(f"BARN_OWL_{suffix}", str(tmp_path / f"legacy-{suffix}"))
    old = Store()
    assert old.data_dir == tmp_path / "legacy-DATA_DIR"
    assert old.events_file == tmp_path / "legacy-EVENTS_FILE"
    for suffix in ("DATA_DIR", "EVENTS_FILE"):
        monkeypatch.setenv(f"NIGHT_OWL_{suffix}", str(tmp_path / f"current-{suffix}"))
    new = Store()
    assert new.data_dir == tmp_path / "current-DATA_DIR"
    assert new.events_file == tmp_path / "current-EVENTS_FILE"
    explicit = Store(data_dir=tmp_path, events_file=tmp_path / "explicit.jsonl")
    assert explicit.data_dir == tmp_path
    assert explicit.events_file == tmp_path / "explicit.jsonl"
