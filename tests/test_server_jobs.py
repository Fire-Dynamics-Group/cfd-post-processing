"""HTTP-shape tests for the sidecar's /jobs endpoints.

These pin the contract the frontend depends on. They use an injected fake
orchestrator instead of the real CFD pipeline so the tests stay fast and
don't require a real run dir on disk.

Pinned contracts (mirror cfd_dashboard.py vocabulary):

- ``POST /jobs`` returns 202 + ``{"job_id": ...}`` on success.
- ``POST /jobs`` returns 409 when a job is already running.
- ``POST /jobs`` returns 422 for missing required fields (FastAPI default).
- ``GET /jobs/{id}`` returns 404 for unknown ids.
- ``GET /jobs/{id}`` returns the polled JobState payload, with ``status``
  transitioning ``running -> completed`` for a happy-path run, and
  ``output_path`` populated on completion.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient

from pipeline.server import create_app
from pipeline.services.job import Step
from pipeline.services.report import ReportRequest, ReportResult


def _payload(path: Path, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "PATH": str(path),
        "CLIENT_NAME": "Acme",
        "PROJECT_NAME": "TestProj",
        "PROJECT_LOCATION": "London",
        "EMAIL_PREFIX": "ian",
        "HAS_EXTENDED_TRAVEL": True,
        "MAX_TD": 15,
        "GUIDANCE": "BS9991",
    }
    base.update(overrides)
    return base


def _make_fake_orchestrator(*, hold: threading.Event | None = None) -> Callable:
    """Build a fake orchestrator that emits each phase, optionally blocking
    until ``hold`` is set so tests can race a second POST against an
    in-flight job."""

    def fake(req: ReportRequest, on_progress) -> ReportResult:
        for step in (Step.PARSING, Step.CHARTING, Step.DRAWING, Step.RENDERING, Step.SAVING):
            on_progress(step, 0.0)
            if hold is not None:
                # Block here so the test can observe a 409 mid-run.
                hold.wait(timeout=5)
            on_progress(step, 1.0)
        out_dir = Path(req.OUTPUT_DIR or req.PATH)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{req.PROJECT_NAME}-fake.docx"
        out_path.write_bytes(b"fake-docx-bytes")
        return ReportResult(output_path=str(out_path), warnings=[])

    return fake


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app(orchestrator=_make_fake_orchestrator()))


def _wait_for_terminal(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] != "running":
            return body
        time.sleep(0.05)
    pytest.fail(f"job {job_id} did not finish within {timeout}s")


def test_health_returns_alive(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


def test_post_jobs_returns_202_and_job_id(client: TestClient, tmp_path: Path) -> None:
    resp = client.post("/jobs", json=_payload(tmp_path))
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body and isinstance(body["job_id"], str)


def test_post_jobs_returns_422_for_missing_field(client: TestClient, tmp_path: Path) -> None:
    body = _payload(tmp_path)
    del body["PROJECT_NAME"]
    resp = client.post("/jobs", json=body)
    assert resp.status_code == 422


def test_get_jobs_returns_404_for_unknown_id(client: TestClient) -> None:
    resp = client.get("/jobs/does-not-exist")
    assert resp.status_code == 404


def test_get_jobs_returns_running_then_completed(client: TestClient, tmp_path: Path) -> None:
    resp = client.post("/jobs", json=_payload(tmp_path))
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    body = _wait_for_terminal(client, job_id)
    assert body["status"] == "completed"
    assert body["step"] == "done"
    assert body["progress_pct"] == 1.0
    assert body["output_path"] is not None
    assert Path(body["output_path"]).exists()


def test_post_jobs_returns_409_while_a_job_is_running(tmp_path: Path) -> None:
    # Use a held fake orchestrator so the first job is provably still running
    # when we issue the second POST.
    hold = threading.Event()
    app = create_app(orchestrator=_make_fake_orchestrator(hold=hold))
    client = TestClient(app)

    first = client.post("/jobs", json=_payload(tmp_path))
    assert first.status_code == 202
    try:
        second = client.post("/jobs", json=_payload(tmp_path))
        assert second.status_code == 409
        assert "already running" in second.json()["detail"].lower()
    finally:
        hold.set()
        _wait_for_terminal(client, first.json()["job_id"])


def test_post_jobs_succeeds_after_previous_job_completes(
    client: TestClient, tmp_path: Path
) -> None:
    first = client.post("/jobs", json=_payload(tmp_path))
    assert first.status_code == 202
    _wait_for_terminal(client, first.json()["job_id"])

    second = client.post("/jobs", json=_payload(tmp_path))
    assert second.status_code == 202
    _wait_for_terminal(client, second.json()["job_id"])


def test_output_path_uses_output_dir_when_provided(client: TestClient, tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    payload = _payload(runs_dir, OUTPUT_DIR=str(out_dir))
    resp = client.post("/jobs", json=payload)
    assert resp.status_code == 202
    body = _wait_for_terminal(client, resp.json()["job_id"])

    assert body["status"] == "completed"
    assert Path(body["output_path"]).parent == out_dir


def test_unexpected_orchestrator_failure_reports_internal_error(tmp_path: Path) -> None:
    """An *unexpected* exception (anything not derived from PipelineError)
    surfaces as ``InternalError`` so the UI shows the [Copy diagnostic]
    affordance for bug reports."""

    def boom(req: ReportRequest, on_progress) -> ReportResult:
        on_progress(Step.PARSING, 0.0)
        raise RuntimeError("simulated bug")

    app = create_app(orchestrator=boom)
    client = TestClient(app)
    resp = client.post("/jobs", json=_payload(tmp_path))
    assert resp.status_code == 202
    body = _wait_for_terminal(client, resp.json()["job_id"])

    assert body["status"] == "failed"
    assert body["error"]["type"] == "InternalError"
    assert "simulated bug" in body["error"]["message"]
    assert body["error"]["step"] == "parsing"
    assert body["error"]["traceback"]


def test_pipeline_error_reports_as_pipeline_error_type(tmp_path: Path) -> None:
    """Expected pipeline failures (missing scenarios, malformed inputs)
    surface as ``PipelineError`` — the UI shows step+message but no Copy
    Diagnostic, since this isn't a bug to file."""
    from pipeline.services.report import PipelineError

    def fail(req: ReportRequest, on_progress) -> ReportResult:
        on_progress(Step.PARSING, 0.0)
        raise PipelineError("No scenarios found in runs directory")

    app = create_app(orchestrator=fail)
    client = TestClient(app)
    resp = client.post("/jobs", json=_payload(tmp_path))
    assert resp.status_code == 202
    body = _wait_for_terminal(client, resp.json()["job_id"])

    assert body["status"] == "failed"
    assert body["error"]["type"] == "PipelineError"
    assert "No scenarios found" in body["error"]["message"]
    assert body["error"]["step"] == "parsing"
