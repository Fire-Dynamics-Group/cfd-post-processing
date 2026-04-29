"""Tests for pipeline.services.job — JobRegistry, JobState, JobError.

These pin the contract the FastAPI sidecar relies on:

- The 409-Conflict guarantee: ``try_create`` is atomic. We must not see two
  callers each receive a fresh JobState when they race in parallel.
- The ring-buffer eviction: completed jobs are dropped FIFO once capacity is
  exceeded, never the currently-running one.
- The status / step / error wire shape: the frontend polls ``to_dict()`` and
  parses an enum-stringified payload.
"""
from __future__ import annotations

import threading

import pytest

from pipeline.services.job import (
    ErrorType,
    JobError,
    JobRegistry,
    JobState,
    JobStatus,
    Step,
)


def test_try_create_returns_running_state_with_unique_id() -> None:
    reg = JobRegistry(capacity=10)
    a = reg.try_create()
    b = reg.try_create()  # first one is still running, so this must be None

    assert a is not None
    assert a.status is JobStatus.RUNNING
    assert a.step is Step.QUEUED
    assert a.progress_pct == 0.0
    assert b is None  # 409 path

    # Once the first completes, a fresh slot opens.
    reg.update(a.id, status=JobStatus.COMPLETED, step=Step.DONE)
    c = reg.try_create()
    assert c is not None
    assert c.id != a.id


def test_try_create_is_atomic_under_concurrent_callers() -> None:
    """Race regression: two threads calling try_create at the same time must
    produce exactly one JobState; the other must get None."""
    reg = JobRegistry(capacity=10)
    barrier = threading.Barrier(8)
    results: list[JobState | None] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        state = reg.try_create()
        with lock:
            results.append(state)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    granted = [r for r in results if r is not None]
    rejected = [r for r in results if r is None]
    assert len(granted) == 1, f"expected exactly one winner, got {len(granted)}"
    assert len(rejected) == 7


def test_ring_buffer_evicts_oldest_completed_job() -> None:
    reg = JobRegistry(capacity=3)
    ids = []
    for _ in range(5):
        state = reg.try_create()
        assert state is not None
        ids.append(state.id)
        reg.update(state.id, status=JobStatus.COMPLETED, step=Step.DONE)

    # Only the last 3 should be retrievable.
    assert reg.get(ids[0]) is None
    assert reg.get(ids[1]) is None
    assert reg.get(ids[2]) is not None
    assert reg.get(ids[3]) is not None
    assert reg.get(ids[4]) is not None


def test_get_returns_none_for_unknown_id() -> None:
    reg = JobRegistry()
    assert reg.get("does-not-exist") is None


def test_update_is_noop_for_unknown_id() -> None:
    reg = JobRegistry()
    # Should not raise.
    reg.update("nope", status=JobStatus.COMPLETED)


def test_update_mutates_known_job() -> None:
    reg = JobRegistry()
    state = reg.try_create()
    assert state is not None
    reg.update(state.id, step=Step.RENDERING, progress_pct=0.42)

    refreshed = reg.get(state.id)
    assert refreshed is not None
    assert refreshed.step is Step.RENDERING
    assert refreshed.progress_pct == 0.42


def test_to_dict_serializes_enums_to_strings() -> None:
    state = JobState(
        id="abc",
        status=JobStatus.RUNNING,
        step=Step.CHARTING,
        progress_pct=0.5,
    )
    payload = state.to_dict()
    assert payload["id"] == "abc"
    assert payload["status"] == "running"
    assert payload["step"] == "charting"
    assert payload["progress_pct"] == 0.5
    assert payload["output_path"] is None
    assert payload["warnings"] == []
    assert payload["error"] is None


def test_to_dict_serializes_error_payload() -> None:
    state = JobState(
        id="abc",
        status=JobStatus.FAILED,
        step=Step.PARSING,
        error=JobError(
            type=ErrorType.PIPELINE,
            message="missing devc.csv",
            step=Step.PARSING,
            details={"scenario": "FS1_FSA"},
            traceback="Traceback...\n",
        ),
    )
    payload = state.to_dict()
    assert payload["status"] == "failed"
    error = payload["error"]
    assert error == {
        "type": "PipelineError",
        "message": "missing devc.csv",
        "step": "parsing",
        "details": {"scenario": "FS1_FSA"},
        "traceback": "Traceback...\n",
    }


@pytest.mark.parametrize(
    "running_status,should_block",
    [
        (JobStatus.RUNNING, True),
        (JobStatus.COMPLETED, False),
        (JobStatus.FAILED, False),
    ],
)
def test_try_create_only_blocks_when_a_job_is_actively_running(
    running_status: JobStatus, should_block: bool
) -> None:
    reg = JobRegistry()
    first = reg.try_create()
    assert first is not None
    reg.update(first.id, status=running_status)

    second = reg.try_create()
    if should_block:
        assert second is None
    else:
        assert second is not None
        assert second.id != first.id
