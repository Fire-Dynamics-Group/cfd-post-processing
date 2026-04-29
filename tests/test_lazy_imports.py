"""Cold-start optimisation: heavy scientific stack stays out of the
import-time graph for `pipeline.services.report`.

PR 3 decision #17. Top-level imports of matplotlib / fdsreader / lxml /
docx / docxtpl / cv2 / fitz / reportlab / PIL add ~2-4s to a bundled-exe
cold start, on top of the PyInstaller bootloader cost. Moving them into
function bodies hides the cost behind the first job's run, which already
takes 50s+.

Run in a fresh subprocess so prior tests' imports don't pollute
``sys.modules``.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


HEAVY_MODULES = [
    "matplotlib",
    "fdsreader",
    "lxml",
    "docx",
    "docxtpl",
    "cv2",
    "fitz",
    "reportlab",
    "PIL",
]


def test_importing_report_module_does_not_pull_heavy_stack():
    project_root = Path(__file__).resolve().parents[1]
    heavy_list = json.dumps(HEAVY_MODULES)
    code = (
        "import sys, os, json; "
        "sys.path.insert(0, os.getcwd()); "
        "sys.path.insert(0, os.path.join(os.getcwd(), 'pipeline')); "
        "import pipeline.services.report as _report; "
        f"deferred = {heavy_list}; "
        "leaked = sorted(m for m in deferred if m in sys.modules); "
        "print(json.dumps(leaked))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"subprocess failed (exit {result.returncode}):\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    last_line = result.stdout.strip().splitlines()[-1]
    leaked = json.loads(last_line)
    assert leaked == [], (
        f"Heavy modules leaked at import time: {leaked}. "
        "Move these imports inside the function bodies that need them."
    )
