"""End-to-end smoke test that actually spawns ``python -m pipeline.server``
and hits it over HTTP — the same way Tauri does in dev.

The in-process FastAPI ``TestClient`` tests catch logic bugs but miss things
like port binding, the ``sys.path`` insert ordering in ``server.py``, the
``--port`` CLI argument, and uvicorn startup. This test covers that gap.

Marked slow because it pays uvicorn startup cost (~1–2s).
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
def test_spawned_sidecar_serves_jobs_endpoint(tmp_path: Path) -> None:
    port = _pick_free_port()

    env = os.environ.copy()
    # Match how Tauri spawns dev: cwd at project root.
    proc = subprocess.Popen(
        [sys.executable, "-m", "pipeline.server", "--port", str(port)],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        _wait_for_health(port)

        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        payload = {
            "PATH": str(runs_dir),
            "CLIENT_NAME": "Acme",
            "PROJECT_NAME": "SpawnSmoke",
            "PROJECT_LOCATION": "London",
            "EMAIL_PREFIX": "ian",
            "HAS_EXTENDED_TRAVEL": True,
            "MAX_TD": 15,
            "GUIDANCE": "BS9991",
            "OUTPUT_DIR": str(out_dir),
        }

        r = httpx.post(f"http://127.0.0.1:{port}/jobs", json=payload, timeout=5)
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]

        deadline = time.time() + 10
        body: dict = {}
        while time.time() < deadline:
            rr = httpx.get(f"http://127.0.0.1:{port}/jobs/{job_id}", timeout=2)
            assert rr.status_code == 200
            body = rr.json()
            if body["status"] != "running":
                break
            time.sleep(0.2)

        # The point of THIS test is the spawn-and-HTTP integration (port
        # binding, sys.path tweak, --port arg, FastAPI threading) — not
        # the full CFD pipeline. A tmp_path has no FDS scenarios, so the
        # real orchestrator correctly fails with a structured PipelineError.
        # That's the success criterion here: "we got a clean terminal
        # response with our structured error shape over HTTP".
        assert body.get("status") == "failed", body
        assert body["error"] is not None
        assert body["error"]["type"] == "PipelineError"
        # tmp_path has no FDS files, so the parser complains about that.
        msg = body["error"]["message"].lower()
        assert "scenario" in msg or "no fds file" in msg
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
