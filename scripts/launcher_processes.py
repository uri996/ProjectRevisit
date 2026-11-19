"""Own only launcher-created processes, including descendants on Windows."""

import ctypes
import json
import os
import subprocess
import threading
import time
from ctypes import wintypes

READY = "PROJECTREVISIT_READY"
CONFIG = "PROJECTREVISIT_CONFIG:"


class LaunchError(Exception):
    """A sanitized startup error; never include raw provider or OS exceptions."""


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong),
        ("job_time", ctypes.c_longlong),
        ("flags", wintypes.DWORD),
        ("minimum_working_set", ctypes.c_size_t),
        ("maximum_working_set", ctypes.c_size_t),
        ("active_process_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority_class", wintypes.DWORD),
        ("scheduling_class", wintypes.DWORD),
    ]


class _IOCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "read_operations",
            "write_operations",
            "other_operations",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io", _IOCounters),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


class ProcessJob:
    """An unnamed, non-inheritable kill-on-close Windows Job Object.

    Workers wait for START on stdin before doing any work. Assignment therefore
    precedes imports, socket binding, Vite config loading and descendant creation.
    """

    def __init__(self):
        self.handle = None
        if os.name != "nt":
            return
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self.api.SetInformationJobObject.restype = wintypes.BOOL
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.AssignProcessToJobObject.restype = wintypes.BOOL
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.handle = self.api.CreateJobObjectW(None, None)
        info = _ExtendedLimits()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.api.SetInformationJobObject(
            self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)
        ):
            self.close()
            raise LaunchError(
                "Cannot create the Windows process cleanup group. No service started."
            )

    def assign(self, process):
        if self.handle and not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise LaunchError("Cannot safely manage the child process. Startup cancelled.")

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


class Child:
    def __init__(self, job, command, cwd, env, label):
        self.label, self.ready, self.config = label, threading.Event(), None
        self.process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            job.assign(self.process)
            self.process.stdin.write("START\n")
            self.process.stdin.flush()
        except Exception:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process.stdin.close()
            self.process.stdout.close()
            raise
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.process.stdout:
            line = line.rstrip()
            if line == READY:
                self.ready.set()
            elif line.startswith(CONFIG):
                try:
                    self.config = json.loads(line[len(CONFIG) :])
                except ValueError:
                    pass
            elif line:
                print(f"[{self.label}] {line}", flush=True)

    def stop(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write("STOP\n")
                self.process.stdin.flush()
            except (OSError, ValueError):
                pass

    def close_pipes(self):
        self.reader.join(timeout=1)
        for pipe in (self.process.stdin, self.process.stdout):
            pipe.close()


def stop_children(children, job):
    try:
        for child in reversed(children):
            child.stop()
        deadline = time.monotonic() + 5
        for child in reversed(children):
            try:
                child.process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
    finally:
        job.close()  # Also reaps grandchildren, even if a worker has already exited.
    for child in children:
        if child.process.poll() is None:
            child.process.terminate()
        child.process.wait(timeout=5)
        child.close_pipes()
