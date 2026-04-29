"""In-memory job state for the report pipeline.

The sidecar runs one report job at a time. We keep a small ring-buffer of
recent jobs so the frontend can poll completed jobs immediately after a
restart-free re-run, without persisting anything across sidecar restarts.

Status names mirror the company's existing
``backendForNextApp/routers/cfd_dashboard.py`` convention so we don't fork
vocabulary across the codebase: ``running | completed | failed``. (We don't
have a queueing layer locally, so there's no ``queued`` *job* status — the
``Step`` enum still exposes a QUEUED *phase* covering the brief window
between ``try_create`` and the first ``on_progress`` callback.)
"""
from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ErrorType(str, Enum):
    VALIDATION = "ValidationError"
    PIPELINE = "PipelineError"
    INTERNAL = "InternalError"


class Step(str, Enum):
    QUEUED = "queued"
    PARSING = "parsing"
    CHARTING = "charting"
    DRAWING = "drawing"
    RENDERING = "rendering"
    SAVING = "saving"
    DONE = "done"


class JobStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobError:
    type: ErrorType
    message: str
    step: Step | None = None
    details: dict[str, Any] | None = None
    traceback: str | None = None


@dataclass
class JobState:
    id: str
    status: JobStatus = JobStatus.RUNNING
    step: Step = Step.QUEUED
    progress_pct: float = 0.0
    output_path: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: JobError | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["step"] = self.step.value
        if self.error is not None:
            d["error"] = {
                "type": self.error.type.value,
                "message": self.error.message,
                "step": self.error.step.value if self.error.step else None,
                "details": self.error.details,
                "traceback": self.error.traceback,
            }
        return d


class JobRegistry:
    """Thread-safe ring buffer of the last ``capacity`` jobs.

    ``try_create`` is the *only* atomic create-or-409 entry point. Callers
    must not check ``has_running()`` and then call a separate ``create()`` —
    that's the race the FastAPI handler used to have.
    """

    def __init__(self, capacity: int = 10) -> None:
        self.capacity = capacity
        self._jobs: OrderedDict[str, JobState] = OrderedDict()
        self._lock = threading.Lock()

    def try_create(self) -> JobState | None:
        """Atomically: if no job is currently running, create one and return
        it. Otherwise return ``None`` (caller should respond 409)."""
        with self._lock:
            for j in self._jobs.values():
                if j.status is JobStatus.RUNNING:
                    return None
            job_id = uuid.uuid4().hex
            state = JobState(id=job_id)
            self._jobs[job_id] = state
            self._evict_locked()
            return state

    def get(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)

    def _evict_locked(self) -> None:
        """Drop oldest non-running entries until we're at capacity.

        Caller must already hold ``self._lock``. Never evicts a running job —
        if every slot is RUNNING we keep them (the registry briefly grows
        past capacity); in practice we enforce one-running-at-a-time so this
        is a single-entry safety guard.
        """
        while len(self._jobs) > self.capacity:
            for jid, j in list(self._jobs.items()):
                if j.status is not JobStatus.RUNNING:
                    del self._jobs[jid]
                    break
            else:
                return
