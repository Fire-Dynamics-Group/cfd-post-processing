"""Pin the sidecar's --log-dir behaviour.

Tauri passes ``--log-dir %LOCALAPPDATA%\\CFDPostProcessing\\logs`` to the
sidecar at spawn so post-mortem debugging on a user's machine has
something to read. This test runs the same CLI in a subprocess and
asserts the file shows up with content.

Marked slow (subprocess + uvicorn startup).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            if r.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(0.2)
    pytest.fail(f"sidecar /health never went green: {last_err}")


@pytest.mark.slow
def test_log_dir_creates_rotating_sidecar_log(tmp_path: Path) -> None:
    port = _pick_free_port()
    log_dir = tmp_path / "logs"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pipeline.server",
            "--port",
            str(port),
            "--log-dir",
            str(log_dir),
        ],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        _wait_for_health(port)
        # Hit /health once more to ensure at least one log line is emitted.
        httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
        time.sleep(0.3)  # give the file handler a beat to flush

        log_file = log_dir / "sidecar.log"
        assert log_file.exists(), f"expected {log_file}"
        contents = log_file.read_text(encoding="utf-8", errors="replace")
        # Anything non-empty proves logging is wired through; specific
        # content like the uvicorn "Started server" line is unstable across
        # versions, so just check the file isn't empty.
        assert contents.strip(), "sidecar.log is empty"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@pytest.mark.slow
def test_no_log_dir_means_no_file_handler(tmp_path: Path) -> None:
    """When ``--log-dir`` is omitted the sidecar must NOT create a log dir
    of its own — Tauri may launch us in dev without one, and we shouldn't
    invent a path silently."""
    port = _pick_free_port()

    # cwd=tmp_path so anything the sidecar writes "in CWD" lands here and
    # we can spot it. PYTHONPATH lets `python -m pipeline.server` still
    # find the package without needing to chdir into project root.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    proc = subprocess.Popen(
        [sys.executable, "-m", "pipeline.server", "--port", str(port)],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        _wait_for_health(port)
        # No log dir should have been created in tmp_path.
        assert not (tmp_path / "logs").exists()
        assert not (tmp_path / "sidecar.log").exists()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
