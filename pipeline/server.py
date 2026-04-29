"""FastAPI sidecar for the CFD Post-Processing desktop app.

Endpoints:
- ``GET  /health``           — liveness probe used by Tauri before the UI loads.
- ``POST /jobs``             — kick off a report-generation job, returns ``{job_id}``.
- ``GET  /jobs/{job_id}``    — poll job state (step / progress_pct / error / output_path).
- ``POST /generate-charts``  — charts-only mode: render PNGs per scenario, return manifest.
- ``GET  /charts/{job}/...`` — static mount serving the generated PNGs.

The sidecar runs one report job at a time. ``POST /jobs`` while a job is
running returns ``409 Conflict``. Charts-only mode is synchronous and
runs in the request handler — there is no background queue and no 409
gate (the frontend disables the Create Charts button while a request is
in flight).

Usage:
    python -m pipeline.server --port 9999
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import threading
import traceback
import uuid
from pathlib import Path
from typing import Any

# Ensure top-level pipeline modules (helper_functions, fds_output_utils, …)
# import cleanly when services/report.py reaches into the vendored pipeline.
# Mirrors what tests/conftest.py already does. (Q13 in PR2_PLAN.md.)
_PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
if _PIPELINE_DIR not in sys.path:
    sys.path.insert(0, _PIPELINE_DIR)

# In a PyInstaller bundle, chdir to the MEIPASS extraction dir so legacy
# relative-path lookups in vendored modules (e.g. report_draw.create_legend's
# ``ImageFont.truetype('SEGOEUIL.TTF', ...)``) find their bundled
# resources. _MEIPASS is unset under a normal Python interpreter, so this
# is a no-op in dev / CI. (PR 3.)
_meipass = getattr(sys, "_MEIPASS", None)
if _meipass:
    os.chdir(_meipass)

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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


# Where /generate-charts writes its PNGs and what /charts serves. Per-job
# subdirectories keep concurrent requests (or a "new run" after an
# unfinished one) from clobbering each other. ``tempfile.gettempdir()``
# resolves to ``%LOCALAPPDATA%\Temp`` on Windows — fine for ephemeral
# render output, cleaned by the OS.
CHARTS_BASE = os.path.join(tempfile.gettempdir(), "cfd_post_processing_charts")


class ChartsRequest(BaseModel):
    """Charts-only payload — mirrors legacy ``run_only_charts.py``."""

    PATH: str = Field(..., description="Path to runs' root directory")
    PROJECT_NAME: str


# Lazy-loaded chart helpers. Kept as module-level attributes (rather than
# function-scoped imports) so tests can pre-populate them via
# ``monkeypatch.setattr(server, "run_hrr_charts", ...)``. The ``hrr_graph``
# module pulls matplotlib at import time (~70 % of the bundled-exe
# cold-start cost — see PR 3 decision #17), so we hold off until the first
# /generate-charts call. The ``is None`` guards in
# ``_ensure_chart_imports`` short-circuit when a test has already
# overridden the slot, preserving the monkeypatch contract.
return_paths_to_files = None
run_hrr_charts = None
run_devc_charts = None


def _ensure_chart_imports() -> None:
    global return_paths_to_files, run_hrr_charts, run_devc_charts
    if return_paths_to_files is None:
        from helper_functions import return_paths_to_files as _rptf
        return_paths_to_files = _rptf
    if run_hrr_charts is None:
        from hrr_graph import run_hrr_charts as _rhc
        run_hrr_charts = _rhc
    if run_devc_charts is None:
        from hrr_graph import run_devc_charts as _rdc
        run_devc_charts = _rdc


# Charts-job registry. Separate from the report-flow JobRegistry because
# its state shape (Step enum, output_path) doesn't fit charts-mode's
# progressive-scenarios contract. Ring buffer of CHARTS_JOBS_CAPACITY most
# recent jobs to bound memory; old entries are evicted in insertion order.
_charts_jobs: dict[str, dict[str, Any]] = {}
_charts_jobs_lock = threading.Lock()
CHARTS_JOBS_CAPACITY = 10


def _snapshot_charts_job(state: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-enough copy of a charts-job state for safe handoff
    to a JSON response. Callers see a frozen view; mutations by the
    worker thread between snapshot and serialisation are invisible."""
    return {
        **state,
        "scenarios": [
            {**s, "charts": [dict(c) for c in s["charts"]]}
            for s in state["scenarios"]
        ],
        "errors": list(state["errors"]),
    }


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

    os.makedirs(CHARTS_BASE, exist_ok=True)

    app = FastAPI(title="CFD Post-Processing Sidecar", version="0.2.0")
    registry = JobRegistry(capacity=10)
    app.state.registry = registry
    app.state.orchestrator = orchestrator

    app.mount("/charts", StaticFiles(directory=CHARTS_BASE), name="charts")

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

    @app.post("/generate-charts", status_code=202)
    def start_charts_job(req: ChartsRequest) -> dict[str, str]:
        if not os.path.isdir(req.PATH):
            raise HTTPException(status_code=400, detail=f"PATH not found: {req.PATH}")

        job_id = uuid.uuid4().hex
        with _charts_jobs_lock:
            while len(_charts_jobs) >= CHARTS_JOBS_CAPACITY:
                oldest = next(iter(_charts_jobs))
                del _charts_jobs[oldest]
            _charts_jobs[job_id] = {
                "job_id": job_id,
                "status": "running",
                "project_name": req.PROJECT_NAME,
                "scenarios": [],
                "scenarios_total": 0,
                "errors": [],
                "error": None,
            }

        threading.Thread(
            target=_run_charts_job,
            args=(job_id, req),
            daemon=True,
            name=f"charts-{job_id[:8]}",
        ).start()
        return {"job_id": job_id}

    @app.get("/generate-charts/{job_id}")
    def get_charts_job(job_id: str) -> dict[str, Any]:
        with _charts_jobs_lock:
            state = _charts_jobs.get(job_id)
            if state is None:
                raise HTTPException(status_code=404, detail="Unknown charts job")
            return _snapshot_charts_job(state)

    return app


def _run_charts_job(job_id: str, req: ChartsRequest) -> None:
    """Worker thread for /generate-charts.

    Iterates over scenario subdirs in deterministic (sorted) order. For
    each one: lazy-imports the chart helpers, runs ``run_hrr_charts`` +
    ``run_devc_charts``, then atomically appends the new scenario's
    manifest entry to the registry so polling clients see it immediately.
    Subdirs whose ``return_paths_to_files`` reports errors are skipped
    and their errors surfaced into the registry.
    """
    try:
        _ensure_chart_imports()

        root = req.PATH
        sub_folders = sorted(
            f for f in os.listdir(root) if os.path.isdir(os.path.join(root, f))
        )
        if not sub_folders:
            sub_folders = [os.path.basename(os.path.dirname(root))]
            root = os.path.dirname(root)

        with _charts_jobs_lock:
            _charts_jobs[job_id]["scenarios_total"] = len(sub_folders)

        job_dir = os.path.join(CHARTS_BASE, job_id)
        os.makedirs(job_dir, exist_ok=True)

        for name in sub_folders:
            scenario_dir = os.path.join(job_dir, name)
            os.makedirs(scenario_dir, exist_ok=True)

            firefighting = "FSA" in name
            (
                path_to_hrr_file,
                _path_to_scen_directory,
                path_to_fds_file,
                path_to_devc_file,
                error_list,
            ) = return_paths_to_files(
                scenario_name=name, dir_path=root, new_folder_structure=True
            )
            if error_list:
                # See the charts-mode skip note in the previous commit.
                with _charts_jobs_lock:
                    _charts_jobs[job_id]["errors"].extend(error_list)
                try:
                    os.rmdir(scenario_dir)
                except OSError:
                    pass
                continue

            run_hrr_charts(
                path_to_fds_file,
                path_to_hrr_file,
                new_dir_path=scenario_dir,
                firefighting=firefighting,
            )
            run_devc_charts(
                path_to_devc_file,
                path_to_fds_file,
                scenario_dir,
                firefighting=firefighting,
            )

            chart_files = sorted(
                f for f in os.listdir(scenario_dir) if f.lower().endswith(".png")
            )
            scenario_entry = {
                "name": name,
                "charts": [
                    {
                        "filename": fn,
                        "url": f"/charts/{job_id}/{name}/{fn}",
                    }
                    for fn in chart_files
                ],
            }
            with _charts_jobs_lock:
                _charts_jobs[job_id]["scenarios"].append(scenario_entry)

        with _charts_jobs_lock:
            _charts_jobs[job_id]["status"] = "completed"
    except Exception as exc:  # noqa: BLE001 - surface everything to the UI
        with _charts_jobs_lock:
            if job_id in _charts_jobs:
                _charts_jobs[job_id]["status"] = "failed"
                _charts_jobs[job_id]["error"] = f"{type(exc).__name__}: {exc}"
                _charts_jobs[job_id]["traceback"] = traceback.format_exc()
        logger.exception("Unhandled error in charts job %s", job_id)


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
