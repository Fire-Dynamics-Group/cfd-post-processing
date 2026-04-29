"""FastAPI sidecar for the CFD Post-Processing desktop app.

Endpoints:
- ``GET  /health``         — liveness probe used by Tauri before the UI loads.
- ``POST /jobs``           — kick off a report-generation job, returns ``{job_id}``.
- ``GET  /jobs/{job_id}``  — poll job state (step / progress_pct / error / output_path).

The sidecar runs one job at a time. ``POST /jobs`` while a job is running
returns ``409 Conflict``. Job state is in-memory only (ring buffer of 10);
the frontend disables the Create Report button while a job is running.

Usage:
    python -m pipeline.server --port 9999
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

# Ensure top-level pipeline modules (helper_functions, fds_output_utils, …)
# import cleanly when services/report.py reaches into the vendored pipeline.
# Mirrors what tests/conftest.py already does. (Q13 in PR2_PLAN.md.)
_PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
if _PIPELINE_DIR not in sys.path:
    sys.path.insert(0, _PIPELINE_DIR)

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pipeline.services.job import (
    ErrorType,
    JobError,
    JobRegistry,
    JobState,
    JobStatus,
    Step,
)
from pipeline.services.report import (
    PipelineError,
    ReportRequest,
    ReportResult,
    run_orchestrator as _default_orchestrator,
)


# Type alias: the orchestrator contract the server depends on.
# Decoupling lets tests inject a fast fake instead of running the real pipeline.
from typing import Callable
Orchestrator = Callable[[ReportRequest, Callable[[Step, float], None]], ReportResult]

logger = logging.getLogger(__name__)


def _run_job(
    state: JobState,
    req: ReportRequest,
    registry: JobRegistry,
    orchestrator: Orchestrator,
) -> None:
    """Synchronous orchestrator run, executed in a daemon worker thread.

    The orchestrator is CPU-bound (matplotlib, lxml, PIL); offloading it
    keeps the FastAPI event loop free to serve ``GET /jobs/{id}`` polls
    (Q18). We use ``threading.Thread`` directly rather than
    ``asyncio.to_thread`` so the worker is decoupled from the request's
    event loop — important for tests that issue back-to-back POSTs.
    """

    def on_progress(step: Step, pct: float) -> None:
        registry.update(
            state.id,
            step=step,
            progress_pct=max(0.0, min(1.0, float(pct))),
        )

    try:
        result: ReportResult = orchestrator(req, on_progress)
    except PipelineError as exc:
        current = registry.get(state.id)
        step = current.step if current else state.step
        registry.update(
            state.id,
            status=JobStatus.FAILED,
            error=JobError(
                type=ErrorType.PIPELINE,
                message=str(exc),
                step=step,
                traceback=traceback.format_exc(),
            ),
        )
        logger.warning(
            "Pipeline error in orchestrator (job=%s): %s", state.id, exc
        )
        return
    except Exception as exc:  # noqa: BLE001 - surface everything to the UI
        current = registry.get(state.id)
        step = current.step if current else state.step
        registry.update(
            state.id,
            status=JobStatus.FAILED,
            error=JobError(
                type=ErrorType.INTERNAL,
                message=f"{type(exc).__name__}: {exc}",
                step=step,
                traceback=traceback.format_exc(),
            ),
        )
        logger.exception("Unhandled error in orchestrator (job=%s)", state.id)
        return

    registry.update(
        state.id,
        status=JobStatus.COMPLETED,
        step=Step.DONE,
        progress_pct=1.0,
        output_path=result.output_path,
        warnings=result.warnings,
    )


def create_app(orchestrator: Orchestrator | None = None) -> FastAPI:
    """Build the FastAPI app.

    ``orchestrator`` is injectable so tests can supply a fast stub instead
    of running the real CFD pipeline. Production callers (``app =
    create_app()`` at module bottom) get the default.
    """
    if orchestrator is None:
        orchestrator = _default_orchestrator

    app = FastAPI(title="CFD Post-Processing Sidecar", version="0.2.0")
    registry = JobRegistry(capacity=10)
    app.state.registry = registry
    app.state.orchestrator = orchestrator

    # Sidecar binds to 127.0.0.1 — only callers are the Tauri webview and the
    # Vite dev server. Allow any origin for the preflight; no credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "alive"}

    @app.post("/jobs", status_code=202)
    def create_job(req: ReportRequest) -> dict[str, str]:
        state = registry.try_create()
        if state is None:
            raise HTTPException(
                status_code=409,
                detail="A report job is already running",
            )
        threading.Thread(
            target=_run_job,
            args=(state, req, registry, orchestrator),
            daemon=True,
            name=f"orchestrator-{state.id[:8]}",
        ).start()
        return {"job_id": state.id}

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        state = registry.get(job_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Unknown job id")
        return state.to_dict()

    return app


app = create_app()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CFD Post-Processing FastAPI sidecar")
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="TCP port to bind on 127.0.0.1 (default: 8765)",
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default=None,
        help=(
            "Directory to write sidecar.log into (rotating, 5MB x 5). "
            "Tauri passes %%LOCALAPPDATA%%/CFDPostProcessing/logs here. "
            "Omit to disable file logging (stderr stays on)."
        ),
    )
    return parser.parse_args()


def _configure_file_logging(log_dir: str) -> None:
    """Attach a RotatingFileHandler to the root logger.

    5MB x 5 files keeps ~25MB on disk worst-case — plenty for post-mortem
    debugging on a user machine without bloating their AppData.
    """
    from logging.handlers import RotatingFileHandler

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        str(log_path / "sidecar.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # Also attach to uvicorn's loggers so request logs go to the file.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).addHandler(handler)


def main() -> None:
    args = _parse_args()
    if args.log_dir:
        _configure_file_logging(args.log_dir)
        logger.info("sidecar starting on port %d, log_dir=%s", args.port, args.log_dir)
    # ``log_config=None`` keeps the handlers we just attached — uvicorn's
    # default config calls ``dictConfig`` which would otherwise wipe them.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        log_level="info",
        log_config=None,
    )


if __name__ == "__main__":
    main()
