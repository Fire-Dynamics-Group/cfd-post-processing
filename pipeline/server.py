"""FastAPI sidecar for the CFD Post-Processing desktop app (scaffold).

This first-PR server intentionally does NOT call into the vendored pipeline.
It exists to prove the Tauri <-> Python HTTP round-trip works end-to-end.
PR 2 will wire ``/generate-report`` through to the actual report pipeline.

Usage:
    python -m pipeline.server --port 9999
"""
from __future__ import annotations

import argparse
from typing import Literal

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    """Form payload posted by the React frontend.

    Mirrors the 7 PySimpleGUI inputs from the legacy auto_report.py form
    (plus the BS9991/ADB radio).
    """

    PATH: str = Field(..., description="Path to runs' root directory")
    CLIENT_NAME: str
    PROJECT_NAME: str
    PROJECT_LOCATION: str
    EMAIL_PREFIX: str = Field(..., description="Senior's email prefix")
    HAS_EXTENDED_TRAVEL: bool = True
    MAX_TD: float | None = Field(default=None, description="Max travel distance in metres")
    GUIDANCE: Literal["BS9991", "ADB"] = "BS9991"


def create_app() -> FastAPI:
    app = FastAPI(title="CFD Post-Processing Sidecar", version="0.1.0")

    # Sidecar binds to 127.0.0.1, so the only callers are the Tauri webview
    # (origin tauri://localhost or https://tauri.localhost on Windows) and
    # the Vite dev server (http://localhost:1420). Allow any origin for the
    # preflight; credentials are never sent.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "alive"}

    @app.post("/generate-report")
    def generate_report(req: ReportRequest) -> dict:
        # PR 1 scaffold: do NOT invoke the pipeline yet — just echo the
        # validated payload to confirm the round-trip works.
        return {
            "status": "ok",
            "message": "scaffold - pipeline not wired yet",
            "received": req.model_dump(),
        }

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
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
