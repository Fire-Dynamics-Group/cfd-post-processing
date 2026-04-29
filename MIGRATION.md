# Migration

This project is the desktop successor to the legacy `CFDReportGen` tool
(PySimpleGUI + PyInstaller `.exe`). Functionality is being ported over from
the upstream **CFDReportGen** repository on GitHub.

> Upstream repo: https://github.com/Fire-Dynamics-Group/CFDReportGen
> Vendor source: branch `report` at commit `ce4c706` (2026-04-28)

## What is being brought over

- The report-generation pipeline: `pipeline/auto_report.py`, `main.py`,
  `render_doc.py`, `pdfgeneration.py`, `pdf_generator.py`, `Pressure_chart.py`,
  `slice_files.py`, `slice_gui.py`, `slice_to_report.py`, `hrr_graph.py`,
  `validate.py`, `report_draw.py`, `reportgenerator.py`, `scenarios_object.py`,
  helper modules, `constants.py`, `config.py`, `click_grid_points.py`,
  `rename_files.py`, and the `run_*.py` driver scripts.
- The 7-input form (PySimpleGUI in the original) re-implemented as a React
  form that POSTs to the FastAPI sidecar (`/generate-report`).
- The `.docx` template, fonts (`SEGOEUIL.TTF`, `Segoe UI Light.ttf`), logo
  (`FDAI_grey.png/jpg`), references CSV, and the upstream `template/` and
  `CFD Word Template/` asset folders.
- The pytest suite under `tests/` (5 test modules + conftest).

The Python pipeline modules under `pipeline/` are vendored **unchanged** from
upstream. New code lives only in:

- `pipeline/server.py` — FastAPI sidecar wrapping the pipeline.
- `src/` — React + Vite frontend.
- `src-tauri/` — Tauri 2 shell that spawns the sidecar.

## Known issues to address in PR 2

- **Bare imports**: vendored modules use top-level imports like
  `from constants import ...`, `from helper_functions import ...`. These
  resolve when running the modules as scripts from the legacy repo root, but
  break when importing them as `pipeline.<module>` via the sidecar. Either
  patch them to relative imports (`from .constants import ...`) or prepend
  `pipeline/` to `sys.path` inside `server.py`.
- **PySimpleGUI usage**: `auto_report.py`, `main.py`, `scenarios_object.py`,
  `run_only_charts.py`, `slice_gui.py` import `PySimpleGUI`. The error/info
  popups need to be replaced with HTTP responses or logging, otherwise the
  sidecar will block waiting on a hidden dialog.
- **Hardcoded asset paths**: Some modules look for `Template CFD Report.docx`,
  fonts, `references.csv`, and `template/`/`CFD Word Template/` at CWD. The
  sidecar runs with CWD = project root, so the upstream layout has been
  mirrored at the project root to match. When PyInstaller-bundled (PR 3),
  these need to come from the bundled resource dir (Tauri's `resources`
  field already includes `templates/*`).
- **New runtime deps** added in `requirements.txt`: `reportlab`, `pdfrw`,
  `PyPDF2`, `opencv-python`, `PyMuPDF`. Versions pinned to match the late-2023
  pinning era of the rest of the file.

## Status

- [x] PR 1: Tauri ⇄ Python HTTP round-trip scaffold (echo, no pipeline yet).
- [x] PR 1.5: Re-vendor `pipeline/` from `report@ce4c706` (this PR).
- [ ] PR 2: Wire `/generate-report` through to `main.py` / `auto_report.py`.
- [ ] PR 3: Bundle the sidecar via PyInstaller (`pyinstaller-server.spec`)
      and ship via Tauri `bundle.externalBin`.
