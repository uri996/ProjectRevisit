"""Check the default API and bundled Vue app in an isolated temporary data space."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="projectrevisit-smoke-") as temp:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = dict(
            os.environ, PROJECT_RAG_DATA_DIR=temp, STREAMLIT_BROWSER_GATHER_USAGE_STATS="false"
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "scripts/launch_windows.py",
                "--port",
                str(port),
                "--no-browser",
            ],
            cwd=root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        opener = build_opener(ProxyHandler({}))
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Local app exited before healthy; build frontend first")
                try:
                    with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                        assert response.status == 200 and json.load(response) == {"status": "ok"}
                    with opener.open(f"http://127.0.0.1:{port}/chat", timeout=1) as response:
                        assert b"ProjectRevisit" in response.read()
                    print("FastAPI + Vue health: PASS (isolated temporary data, no AI calls)")
                    return
                except (URLError, OSError):
                    time.sleep(0.2)
            raise RuntimeError("Local app health check timed out")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
