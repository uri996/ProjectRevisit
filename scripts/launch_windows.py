"""Windows production/development supervisor; no business or data migrations."""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import socket
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.launcher_processes import (  # noqa: E402
    READY,
    Child,
    LaunchError,
    ProcessJob,
    stop_children,
)


def environment():
    env = dict(os.environ)
    env.update(
        NO_COLOR="1",
        TERM="dumb",
        CLICOLOR="0",
        PYTHONIOENCODING="utf-8",
        PYTHONUNBUFFERED="1",
        ANONYMIZED_TELEMETRY="False",
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
    )
    for key in ("FORCE_COLOR", "CLICOLOR_FORCE"):
        env.pop(key, None)
    return env


def read_command():
    # Raw pipe reads avoid a daemon holding Python's buffered-stdin lock at exit.
    line = bytearray()
    while len(line) < 32:
        byte = os.read(sys.stdin.fileno(), 1)
        if not byte or byte == b"\n":
            break
        line.extend(byte)
    return bytes(line).strip()


def backend_worker(port):
    # Do not initialize the app until the supervisor owns this worker.
    if read_command() != b"START":
        return 1
    os.environ.update(environment())
    with socket.socket() as listener:
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind(("127.0.0.1", port))
            listener.listen(128)
        except OSError:
            print(
                "Backend port is unavailable. Close its existing owner before retrying.", flush=True
            )
            return 1
        try:
            import uvicorn

            from backend.api.app import create_api

            server = uvicorn.Server(
                uvicorn.Config(
                    create_api(port=port),
                    host="127.0.0.1",
                    port=port,
                    access_log=False,
                    use_colors=False,
                    log_level="critical",
                )
            )
            finished = threading.Event()

            def control():
                while (command := read_command()) and command != b"STOP":
                    pass
                server.should_exit = True  # EOF also means the supervisor disappeared.

            def announce():
                while not finished.wait(0.05):
                    if server.started:
                        print(READY, flush=True)
                        return

            threading.Thread(target=control, daemon=True).start()
            threading.Thread(target=announce, daemon=True).start()
            try:
                server.run(sockets=[listener])
            finally:
                finished.set()
            if server.started:
                return 0
        except (Exception, SystemExit):
            pass
    print(
        "Backend startup failed. Check Python dependencies and local data permissions.", flush=True
    )
    return 1


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def wait_ready(child, url, timeout, *, frontend=False, dependencies=()):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for owned in (child, *dependencies):
            if owned.process.poll() is not None:
                raise LaunchError(f"{owned.label} exited before startup completed. No page opened.")
        if child.ready.is_set():
            try:
                with opener.open(url, timeout=0.5) as response:
                    body = response.read(100_000)
                    valid = (
                        b"/@vite/client" in body
                        if frontend
                        else json.loads(body) == {"status": "ok"}
                    )
                    if response.status == 200 and valid:
                        return
            except (URLError, OSError, ValueError):
                pass
        time.sleep(0.1)
    raise LaunchError(
        f"{child.label} readiness timed out. Check configuration and port availability."
    )


def dev_config(child, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.config is not None:
            value = child.config
            try:
                target = urlsplit(value["backend"])
                api_port, port = target.port or 80, value["port"]
                if (
                    value["host"] not in ("127.0.0.1", "localhost")
                    or target.scheme != "http"
                    or target.hostname != "127.0.0.1"
                    or target.username
                    or target.password
                    or target.query
                    or target.fragment
                    or target.path not in ("", "/")
                    or not isinstance(port, int)
                    or isinstance(port, bool)
                    or not 1 <= port <= 65535
                    or not 1 <= api_port <= 65535
                    or port == api_port
                ):
                    raise ValueError
                return api_port, port
            except (KeyError, TypeError, ValueError, AttributeError):
                raise LaunchError(
                    "Vite must use a loopback host and a local HTTP /api proxy with separate ports."
                ) from None
        if child.process.poll() is not None:
            child.reader.join(timeout=0.5)
            if child.config is not None:
                continue
            raise LaunchError(
                "Cannot read Vite configuration. Check Node version, npm ci and frontend/vite.config.ts."
            )
        time.sleep(0.05)
    raise LaunchError("Reading Vite configuration timed out. No service started.")


def supervise(args, stop=None):
    from filelock import FileLock, Timeout

    identity = hashlib.sha256(os.path.normcase(str(ROOT.resolve())).encode()).hexdigest()[:24]
    lock = FileLock(Path(tempfile.gettempdir()) / f"projectrevisit-launch-{identity}.lock")
    try:
        lock.acquire(timeout=0)
    except Timeout:
        raise LaunchError(
            "Another ProjectRevisit launcher is active. Close it before starting another mode."
        ) from None
    children, job = [], None
    try:
        if not args.dev and not args.api_only and not (ROOT / "frontend/dist/index.html").is_file():
            raise LaunchError(
                "Frontend build missing. In frontend run: npm ci, then npm run build."
            )
        for name in ("uvicorn", "fastapi", "multipart"):
            if importlib.util.find_spec(name) is None:
                raise LaunchError(
                    "Python dependencies missing. Follow README.md to install them in .venv."
                )
        job = ProcessJob()
        env = environment()

        def spawn(command, cwd, label):
            child = Child(job, command, cwd, env, label)
            children.append(child)
            return child

        port, vite_port = args.port or 8765, None
        if args.dev:
            node = shutil.which("node")
            if not node or not shutil.which("npm"):
                raise LaunchError("Node.js and npm are required for development. See README.md.")
            if not (ROOT / "frontend/node_modules/vite/bin/vite.js").is_file():
                raise LaunchError("Frontend dependencies missing. In frontend run: npm ci.")
            helper = str(ROOT / "frontend/scripts/launch-dev.mjs")
            inspection = spawn([node, helper, "--inspect-config"], ROOT / "frontend", "Vite config")
            port, vite_port = dev_config(inspection, args.startup_timeout)
            if args.port is not None and args.port != port:
                raise LaunchError(
                    "Development backend port comes from Vite's /api proxy. Update that config instead of --port."
                )
        backend = spawn(
            [
                sys.executable,
                str(ROOT / "scripts/launch_windows.py"),
                "--worker",
                "--port",
                str(port),
            ],
            ROOT,
            "Backend",
        )
        print(f"Starting backend on 127.0.0.1:{port}...", flush=True)
        wait_ready(backend, f"http://127.0.0.1:{port}/api/health", args.startup_timeout)
        print("Backend HTTP health: ready.", flush=True)
        running = [backend]
        url = f"http://127.0.0.1:{port}"
        if args.dev:
            frontend = spawn([node, helper], ROOT / "frontend", "Frontend")
            running.append(frontend)
            url = f"http://127.0.0.1:{vite_port}"
            wait_ready(frontend, url, args.startup_timeout, frontend=True, dependencies=(backend,))
            print("Vite HTTP health: ready (hot reload enabled).", flush=True)
        if any(child.process.poll() is not None for child in running):
            raise LaunchError("A service stopped during startup. No page opened.")
        print(f"ProjectRevisit: {url} (local only). Press Ctrl+C to stop.", flush=True)
        if not args.no_browser and not args.api_only:
            try:
                if not webbrowser.open(url):
                    print(f"Default browser could not be opened. Open {url} manually.", flush=True)
            except Exception:
                print(f"Default browser could not be opened. Open {url} manually.", flush=True)
        stop = stop or threading.Event()
        while not stop.wait(0.2):
            if any(child.process.poll() is not None for child in running):
                raise LaunchError(
                    "A service stopped unexpectedly. Closing this launcher's remaining processes."
                )
        return 0
    finally:
        try:
            if job:
                stop_children(children, job)
        finally:
            lock.release()


def main(argv=None):
    parser = argparse.ArgumentParser(description="ProjectRevisit local Vue + FastAPI application")
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dev", action="store_true", help="Start backend then Vite with hot reload")
    mode.add_argument(
        "--api-only", action="store_true", help="Development API for a manually started Vite"
    )
    parser.add_argument("--startup-timeout", type=float, default=30)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535")
    if not 0 < args.startup_timeout <= 120:
        parser.error("startup-timeout must be greater than 0 and at most 120 seconds")
    if args.worker:
        return backend_worker(args.port or 8765)
    if sys.prefix == sys.base_prefix:
        print("Use .venv\\Scripts\\python.exe; install project dependencies first.")
        return 1
    if os.name == "nt":

        def interrupted(*_):
            raise KeyboardInterrupt

        signal.signal(signal.SIGBREAK, interrupted)
    try:
        return supervise(args)
    except KeyboardInterrupt:
        print("ProjectRevisit stopped. Launcher-owned services closed.", flush=True)
        return 0
    except (LaunchError, OSError, ImportError) as exc:
        print(
            str(exc)
            if isinstance(exc, LaunchError)
            else "Startup failed. Check dependencies, port availability and local permissions.",
            flush=True,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
