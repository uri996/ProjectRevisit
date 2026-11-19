"""Synthetic launcher tests: no OS credentials, private data or model calls."""

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import venv
from argparse import Namespace
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import pytest

from scripts import launch_windows as launcher
from scripts.launcher_processes import Child, LaunchError, ProcessJob, stop_children

ROOT = Path(__file__).resolve().parents[1]


def options(**values):
    defaults = dict(dev=False, api_only=False, port=None, no_browser=False, startup_timeout=3)
    return Namespace(**(defaults | values))


@pytest.fixture
def controlled(tmp_path, monkeypatch):
    (tmp_path / "frontend/dist").mkdir(parents=True)
    (tmp_path / "frontend/dist/index.html").write_text("<title>ProjectRevisit</title>")
    (tmp_path / "frontend/node_modules/vite/bin").mkdir(parents=True)
    (tmp_path / "frontend/node_modules/vite/bin/vite.js").touch()
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher.shutil, "which", lambda name: name)
    events = []

    class Job:
        def close(self):
            events.append("cleanup")

    class FakeChild:
        def __init__(self, job, command, cwd, env, label):
            self.label = label
            self.process = Namespace(poll=lambda: None)
            self.config = {"host": "127.0.0.1", "port": 15173, "backend": "http://127.0.0.1:18765"}
            events.append(("spawn", label))

    monkeypatch.setattr(launcher, "ProcessJob", Job)
    monkeypatch.setattr(launcher, "Child", FakeChild)
    monkeypatch.setattr(
        launcher,
        "wait_ready",
        lambda child, url, *a, **kw: events.append(("ready", child.label, url)),
    )
    monkeypatch.setattr(launcher, "stop_children", lambda children, job: job.close())
    monkeypatch.setattr(
        launcher.webbrowser, "open", lambda url: events.append(("browser", url)) or True
    )
    stop = threading.Event()
    stop.set()
    return events, stop


@pytest.mark.parametrize("dev", [False, True])
def test_browser_opens_once_after_all_owned_services_ready(controlled, dev):
    events, stop = controlled
    args = options()
    args.dev = dev
    assert launcher.supervise(args, stop) == 0
    url = "http://127.0.0.1:15173" if dev else "http://127.0.0.1:8765"
    assert events.count(("browser", url)) == 1
    assert events.index(
        (
            "ready",
            "Backend",
            "http://127.0.0.1:18765/api/health" if dev else "http://127.0.0.1:8765/api/health",
        )
    ) < events.index(("browser", url))
    if dev:
        assert events.index(
            ("ready", "Backend", "http://127.0.0.1:18765/api/health")
        ) < events.index(("spawn", "Frontend"))
        assert events.index(("ready", "Frontend", url)) < events.index(("browser", url))
    assert events[-1] == "cleanup"


@pytest.mark.parametrize("stage", ["Backend", "Frontend"])
def test_failure_at_either_stage_never_opens_browser_and_closes_owned_children(
    controlled, monkeypatch, stage
):
    events, stop = controlled
    args = options()
    args.dev = True

    def fail(child, *args, **kwargs):
        if child.label == stage:
            raise LaunchError("Synthetic startup failure")

    monkeypatch.setattr(launcher, "wait_ready", fail)
    with pytest.raises(LaunchError):
        launcher.supervise(args, stop)
    assert not any(isinstance(e, tuple) and e[0] == "browser" for e in events)
    if stage == "Backend":
        assert ("spawn", "Frontend") not in events
    assert events[-1] == "cleanup"


def test_missing_build_or_node_never_starts_server(controlled, monkeypatch):
    events, stop = controlled
    (launcher.ROOT / "frontend/dist/index.html").unlink()
    with pytest.raises(LaunchError, match="build missing"):
        launcher.supervise(options(), stop)
    assert events == []
    args = options()
    args.dev = True
    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    with pytest.raises(LaunchError, match="Node.js and npm"):
        launcher.supervise(args, stop)
    assert not any(isinstance(e, tuple) and e[0] == "spawn" for e in events)


def test_keyboard_interrupt_still_cleans_owned_services(controlled, monkeypatch):
    events, stop = controlled

    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(launcher.webbrowser, "open", interrupt)
    with pytest.raises(KeyboardInterrupt):
        launcher.supervise(options(), stop)
    assert events[-1] == "cleanup"


def test_unexpected_service_exit_closes_other_owned_services(controlled, monkeypatch):
    events, _ = controlled
    stop = threading.Event()
    original = launcher.Child
    children = []

    def child(*args, **kwargs):
        value = original(*args, **kwargs)
        children.append(value)
        return value

    def browser(url):
        children[-1].process.poll = lambda: 1
        return True

    monkeypatch.setattr(launcher, "Child", child)
    monkeypatch.setattr(launcher.webbrowser, "open", browser)
    with pytest.raises(LaunchError, match="stopped unexpectedly"):
        launcher.supervise(options(dev=True), stop)
    assert events[-1] == "cleanup"


@pytest.mark.skipif(os.name != "nt", reason="Windows batch dispatch")
@pytest.mark.parametrize("filename,expected", [("start.bat", []), ("dev.bat", ["--dev"])])
def test_batch_dispatch_from_directory_with_spaces(tmp_path, filename, expected):
    root = tmp_path / "synthetic launch workspace"
    root.mkdir()
    venv.EnvBuilder(with_pip=False).create(root / ".venv")
    (root / filename).write_bytes((ROOT / filename).read_bytes())
    (root / "scripts").mkdir()
    (root / "scripts/launch_windows.py").write_text(
        "import json,sys; print('SYNTHETIC_ARGS:' + json.dumps(sys.argv[1:]))", encoding="utf-8"
    )
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", str(root / filename)],
        input=b"\r\n",
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0
    import json

    assert ("SYNTHETIC_ARGS:" + json.dumps(expected)).encode() in result.stdout
    assert b"\x1b" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "config",
    [
        {"host": "0.0.0.0", "port": 5173, "backend": "http://127.0.0.1:8765"},
        {"host": "localhost", "port": 5173, "backend": "https://example.com:8765"},
        {"host": "localhost", "port": 5173, "backend": "http://127.0.0.1:5173"},
        {"host": "localhost", "port": 5173, "backend": "http://user:secret@127.0.0.1:8765"},
    ],
)
def test_dev_configuration_stays_loopback_and_does_not_echo_values(config):
    with pytest.raises(LaunchError, match="loopback") as error:
        launcher.dev_config(Namespace(config=config), 1)
    assert "secret" not in str(error.value)


def test_no_http_probe_before_owned_process_readiness_and_wait_is_bounded(monkeypatch):
    opener = Namespace(open=lambda *a, **k: pytest.fail("Must not trust an unrelated listener"))
    monkeypatch.setattr(launcher, "build_opener", lambda *a: opener)
    child = Namespace(
        label="Backend", ready=threading.Event(), process=Namespace(poll=lambda: None)
    )
    start = time.monotonic()
    with pytest.raises(LaunchError, match="timed out"):
        launcher.wait_ready(child, "http://127.0.0.1:1/api/health", 0.1)
    assert time.monotonic() - start < 1


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def port_closed(port):
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def await_closed(ports):
    for _ in range(50):
        if all(port_closed(port) for port in ports):
            return
        time.sleep(0.1)
    pytest.fail("A launcher-owned listener survived shutdown")


def await_http(process, port, path, marker):
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        assert process.poll() is None, "Launcher exited before readiness"
        try:
            with opener.open(f"http://127.0.0.1:{port}{path}", timeout=0.5) as response:
                if marker in response.read():
                    return
        except (URLError, OSError):
            pass
        time.sleep(0.1)
    pytest.fail("Synthetic launcher HTTP readiness timed out")


def test_occupied_backend_is_not_reused_or_misreported(tmp_path):
    with socket.socket() as unrelated:
        unrelated.bind(("127.0.0.1", 0))
        unrelated.listen()
        port = unrelated.getsockname()[1]
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/launch_windows.py"),
                "--api-only",
                "--no-browser",
                "--port",
                str(port),
            ],
            env=dict(os.environ, PROJECT_RAG_DATA_DIR=str(tmp_path)),
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == 1
        assert b"port is unavailable" in result.stdout
        assert b"HTTP health: ready" not in result.stdout
        assert not (tmp_path / "metadata.sqlite3").exists()
        assert unrelated.fileno() != -1


def test_backend_initialization_failure_never_reports_healthy(tmp_path):
    invalid_root = tmp_path / "synthetic-not-a-directory"
    invalid_root.write_text("synthetic fixture")
    port = free_port()
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/launch_windows.py"),
            "--api-only",
            "--no-browser",
            "--port",
            str(port),
        ],
        env=dict(os.environ, PROJECT_RAG_DATA_DIR=str(invalid_root)),
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 1
    assert b"Backend startup failed" in result.stdout
    assert b"HTTP health: ready" not in result.stdout
    assert b"Fatal Python error" not in result.stdout + result.stderr
    assert str(invalid_root).encode() not in result.stdout + result.stderr
    await_closed([port])


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object lifecycle")
def test_job_reaps_grandchild_even_after_worker_exits_and_keeps_unrelated_listener():
    port = free_port()
    grandchild = f"import socket,time; s=socket.socket(); s.bind(('127.0.0.1',{port})); s.listen(); print('PROJECTREVISIT_READY',flush=True); time.sleep(120)"
    code = f"import subprocess,sys; input(); subprocess.Popen([sys.executable,'-u','-c',{grandchild!r}])"
    job = ProcessJob()
    children = []
    with socket.socket() as unrelated:
        unrelated.bind(("127.0.0.1", 0))
        unrelated.listen()
        try:
            child = Child(
                job, [sys.executable, "-u", "-c", code], ROOT, launcher.environment(), "Synthetic"
            )
            children.append(child)
            assert child.ready.wait(10)
            child.process.wait(timeout=5)
            assert not port_closed(port)
        finally:
            stop_children(children, job)
        await_closed([port])
        assert unrelated.fileno() != -1


def test_real_production_start_duplicate_refusal_and_abrupt_cleanup(tmp_path):
    port = free_port()
    command = [
        sys.executable,
        str(ROOT / "scripts/launch_windows.py"),
        "--no-browser",
        "--port",
        str(port),
    ]
    env = dict(os.environ, PROJECT_RAG_DATA_DIR=str(tmp_path))
    process = subprocess.Popen(
        command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    try:
        await_http(process, port, "/", b"ProjectRevisit")
        duplicate = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=10)
        assert duplicate.returncode == 1 and b"launcher is active" in duplicate.stdout
    finally:
        process.terminate()
        output = process.communicate(timeout=10)[0]
    assert b"\x1b" not in output
    await_closed([port])


@pytest.mark.skipif(not shutil.which("node"), reason="Node is required for real Vite startup")
def test_real_dev_sequence_proxy_hot_reload_and_cleanup(tmp_path):
    job = ProcessJob()
    inspector = Child(
        job,
        [shutil.which("node"), str(ROOT / "frontend/scripts/launch-dev.mjs"), "--inspect-config"],
        ROOT / "frontend",
        launcher.environment(),
        "Vite config",
    )
    try:
        backend_port, vite_port = launcher.dev_config(inspector, 10)
    finally:
        stop_children([inspector], job)
    if not all(port_closed(port) for port in (backend_port, vite_port)):
        pytest.skip(
            "Configured development ports already have an owner; no existing service touched"
        )
    env = dict(os.environ, PROJECT_RAG_DATA_DIR=str(tmp_path))
    command = [sys.executable, str(ROOT / "scripts/launch_windows.py"), "--dev", "--no-browser"]
    process = subprocess.Popen(
        command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    try:
        await_http(process, vite_port, "/", b"/@vite/client")
        await_http(process, vite_port, "/api/health", b'"status":"ok"')
        await_http(process, vite_port, "/@vite/client", b"WebSocket")
    finally:
        process.terminate()
        output = process.communicate(timeout=10)[0]
    assert output.index(b"Backend HTTP health: ready") < output.index(b"Vite HTTP health: ready")
    assert b"\x1b" not in output
    await_closed([backend_port, vite_port])

    # Occupying only the frontend must clean the newly created backend on failure.
    with socket.socket() as unrelated:
        unrelated.bind(("127.0.0.1", vite_port))
        unrelated.listen()
        failed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=20)
        assert failed.returncode == 1
        assert b"Vite port is already in use" in failed.stdout
        assert b"ProjectRevisit: http" not in failed.stdout
        await_closed([backend_port])
        assert unrelated.fileno() != -1
