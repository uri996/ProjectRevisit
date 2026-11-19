import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import pytest


def test_new_launcher_help_and_loopback_health_without_frontend_dependency(tmp_path):
    root = Path(__file__).resolve().parents[1]
    help_result = subprocess.run(
        [sys.executable, str(root / "scripts/launch_windows.py"), "--help"],
        env=dict(os.environ, FORCE_COLOR="1"),
        capture_output=True,
        timeout=20,
    )
    assert help_result.returncode == 0
    assert b"FastAPI" in help_result.stdout and b"\x1b" not in help_result.stdout
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [
            sys.executable,
            str(root / "scripts/launch_windows.py"),
            "--api-only",
            "--no-browser",
            "--port",
            str(port),
        ],
        cwd=root,
        env=dict(
            os.environ, PROJECT_RAG_DATA_DIR=str(tmp_path), FORCE_COLOR="1", CLICOLOR_FORCE="1"
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    opener = build_opener(ProxyHandler({}))
    try:
        deadline = time.monotonic() + 20
        while True:
            assert process.poll() is None, "Local launcher stopped unexpectedly"
            try:
                with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                    assert response.status == 200 and b'"status":"ok"' in response.read()
                    break
            except (URLError, OSError):
                assert time.monotonic() < deadline, "Local health timed out"
                time.sleep(0.1)
    finally:
        process.terminate()
        output = process.communicate(timeout=10)[0]
    assert b"\x1b" not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows CMD startup behavior")
def test_batch_launcher_keeps_install_failure_visible(tmp_path):
    root = Path(__file__).resolve().parents[1]
    batch = tmp_path / "start.bat"
    batch.write_bytes((root / "start.bat").read_bytes())
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
