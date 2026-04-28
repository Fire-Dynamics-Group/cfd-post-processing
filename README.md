# CFD Post-Processing

Desktop successor to the legacy `CFDReportGen.exe`. Tauri 2 shell + React (Vite)
frontend + a FastAPI Python sidecar that wraps the existing report pipeline.

This first scaffold proves the Tauri <-> Python HTTP round-trip — the form POSTs
to `/generate-report` and the server echoes the payload. Wiring the form data
through to the actual pipeline is the next PR.

## Layout

```
pipeline/      Vendored pipeline modules (UNCHANGED) + new server.py FastAPI wrapper
tests/         Pytest tests vendored from CFDReportGen
templates/     .docx + reference data shipped with the app
src/           React + Vite frontend
src-tauri/     Tauri shell (Rust) — spawns the sidecar, exposes get_sidecar_port
```

## Dev setup

```bash
# 1. Python venv + deps
python -m venv venv
venv/Scripts/python -m pip install -r requirements.txt

# 2. Frontend deps
npm install

# 3. Run the desktop app (Tauri picks a free port, spawns the sidecar)
npm run dev
```

Tests:

```bash
venv/Scripts/python -m pytest tests/ -v
```

Sidecar standalone (handy for debugging):

```bash
venv/Scripts/python -m pipeline.server --port 9999
curl http://127.0.0.1:9999/health
```

## Production sidecar (follow-up PR)

`pyinstaller-server.spec` builds the FastAPI app into a single `pipeline-server`
binary that Tauri's `bundle.externalBin` will pick up at package time.
