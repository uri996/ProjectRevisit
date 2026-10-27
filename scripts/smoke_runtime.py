"""Start an isolated Streamlit server with synthetic/temp data, check health, stop it."""

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
    with tempfile.TemporaryDirectory(prefix="project-rag-smoke-") as temp:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = dict(
            os.environ, PROJECT_RAG_DATA_DIR=temp, STREAMLIT_BROWSER_GATHER_USAGE_STATS="false"
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "ui/app.py",
                "--server.headless=true",
                f"--server.port={port}",
                "--server.address=127.0.0.1",
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
                    raise RuntimeError("Streamlit exited before becoming healthy")
                try:
                    with opener.open(
                        f"http://127.0.0.1:{port}/_stcore/health", timeout=1
                    ) as response:
                        if response.status == 200 and response.read() == b"ok":
                            print(
                                "Streamlit runtime health: PASS (isolated temporary data, no AI calls)"
                            )
                            return
                except (URLError, OSError):
                    time.sleep(0.2)
            raise RuntimeError("Streamlit health check timed out")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
