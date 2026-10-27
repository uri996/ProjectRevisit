import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_windows_launcher_help_has_no_ansi_even_with_forced_color():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "launch_windows.py"), "--help"],
        env=dict(os.environ, FORCE_COLOR="1", CLICOLOR_FORCE="1"),
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0
    assert b"Usage:" in result.stdout
    assert b"\x1b" not in result.stdout + result.stderr


def test_windows_launcher_runtime_health_and_plain_output(tmp_path):
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(
        os.environ,
        PROJECT_RAG_DATA_DIR=str(tmp_path),
        STREAMLIT_BROWSER_GATHER_USAGE_STATS="false",
        FORCE_COLOR="1",
        CLICOLOR_FORCE="1",
    )
    process = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "scripts" / "launch_windows.py"),
            "--server.headless=true",
            f"--server.port={port}",
            "--server.address=127.0.0.1",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    opener = build_opener(ProxyHandler({}))
    healthy = False
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            assert process.poll() is None, "Launcher stopped before becoming healthy"
            try:
                with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=1) as response:
                    healthy = response.status == 200 and response.read() == b"ok"
                if healthy:
                    break
            except (URLError, OSError):
                time.sleep(0.1)
        assert healthy
    finally:
        process.terminate()
        output = process.communicate(timeout=10)[0]
    assert b"\x1b" not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows CMD startup behavior")
def test_batch_launcher_keeps_install_failure_visible(tmp_path):
    batch = tmp_path / "start.bat"
    batch.write_bytes((ROOT / "start.bat").read_bytes())
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", str(batch)],
        input=b"\r\n",
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 1
    assert b"Please install Python 3.12" in result.stdout
    assert b"\x1b" not in result.stdout + result.stderr
