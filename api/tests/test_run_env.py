"""The launch script reads a local .env without starting the API in these tests."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_run_script_loads_literal_env_and_preserves_shell_values(tmp_path):
    api_dir = tmp_path / "api"
    bin_dir = tmp_path / "bin"
    api_dir.mkdir()
    bin_dir.mkdir()
    run_script = api_dir / "run.sh"
    shutil.copyfile(Path(__file__).resolve().parents[1] / "run.sh", run_script)
    run_script.chmod(0o755)

    keys = ["NO_TEST_EXISTING", "NO_TEST_EMPTY", "NO_TEST_SPACED", "NO_TEST_SINGLE",
            "NO_TEST_DOUBLE", "NO_TEST_HASH", "NO_TEST_COMMENT", "NO_TEST_BLANK",
            "NO_TEST_LITERAL", "NO_TEST_BACKTICK", "NO_TEST_DOLLAR", "HOST", "PORT"]
    fake_uv = bin_dir / "uv"
    fake_uv.write_text(f"#!{sys.executable}\n"
                       "import json, os, sys\n"
                       f"print(json.dumps({{'env': {{key: os.environ.get(key) for key in {keys!r}}}, 'args': sys.argv[1:]}}))\n")
    fake_uv.chmod(0o755)

    marker = tmp_path / "substitution-ran"
    literal = f"$(touch {marker})"
    backtick = f"`touch {marker}`"
    (tmp_path / ".env").write_text(
        "# ignored\n"
        "NO_TEST_EXISTING=from-file\n"
        "NO_TEST_EMPTY=from-file\n"
        " export NO_TEST_SPACED = spaced value # trailing comment\n"
        "NO_TEST_SINGLE='a # literal' # trailing comment\n"
        'NO_TEST_DOUBLE="b # literal" # trailing comment\n'
        "NO_TEST_HASH=abc#def\n"
        "NO_TEST_COMMENT=plain # trailing comment\n"
        "NO_TEST_BLANK= # trailing comment\n"
        f"NO_TEST_LITERAL={literal}\n"
        f"NO_TEST_BACKTICK={backtick}\n"
        "NO_TEST_DOLLAR=$HOME\n"
        "HOST=127.0.0.1 # address\n"
        "PORT=8765 # port\n")
    env = os.environ.copy()
    for key in keys:
        env.pop(key, None)
    env.update({"PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
                "NO_TEST_EXISTING": "from-shell", "NO_TEST_EMPTY": ""})
    process = subprocess.run([str(run_script), "--test-flag"], cwd=tmp_path, env=env,
                             capture_output=True, text=True, check=True, timeout=10)
    result = json.loads(process.stdout)

    assert result["env"] == {
        "NO_TEST_EXISTING": "from-shell", "NO_TEST_EMPTY": "", "NO_TEST_SPACED": "spaced value",
        "NO_TEST_SINGLE": "a # literal", "NO_TEST_DOUBLE": "b # literal", "NO_TEST_HASH": "abc#def",
        "NO_TEST_COMMENT": "plain", "NO_TEST_BLANK": "", "NO_TEST_LITERAL": literal,
        "NO_TEST_BACKTICK": backtick, "NO_TEST_DOLLAR": "$HOME",
        "HOST": "127.0.0.1", "PORT": "8765"}
    assert result["args"] == ["run", "uvicorn", "main:app", "--host", "127.0.0.1",
                              "--port", "8765", "--test-flag"]
    assert not marker.exists()
