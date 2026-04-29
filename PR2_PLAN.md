# PR 2 Plan — Wire `/generate-report` to the pipeline

> Hand-off doc. Designed via `/grill-me` in a previous instance on 2026-04-29.
> Read this end-to-end before touching code; the recommendations chain together.

## Goal

Make the desktop app actually generate a `.docx` report when the user clicks **Create Report**. Today the form POSTs to a stub that echoes its input. After PR 2, it produces the same report the legacy `CFDReportGen.exe` did, end-to-end, locally, in the desktop app.

## Architecture decisions (locked)

| # | Topic | Decision |
|---|---|---|
| 1 | **Entry point** | New `pipeline/services/report.py` that orchestrates building blocks directly. Don't import `auto_report.py` or `main.py` — they're GUI-coupled. Treat them as historical reference for *what* needs to happen, not what to transcribe. |
| 2 | **Invocation model** | Job + polling (mirrors `backendForNextApp/routers/cfd_dashboard.py`). `POST /jobs` → `{ job_id }`; `GET /jobs/{id}` → status. |
| 3 | **Progress shape** | `step` (parsing / charting / drawing / rendering / saving) + `progress_pct` (within-phase). Orchestrator takes a `on_progress: Callable[[str, float], None]` callback. |
| 4 | **Output location** | Default = `PATH` (runs root). Optional `OUTPUT_DIR` override on the form (folder picker). |
| 5 | **Output filename** | `{PROJECT_NAME}-CFD Report-{YYYY-MM-DD}.docx` (legacy is `{PROJECT_NAME}-CFD Report.docx`; date suffix avoids clobbering re-runs). |
| 6 | **Error shape** | Structured payload `{ type: "ValidationError" \| "PipelineError" \| "InternalError", message, step?, details?, traceback? }`. Different UI treatments per type. |
| 7 | **PySimpleGUI** | Strip from the 2 modules in the runtime path: kill the import in `pipeline/scenarios_object.py` (caller is already commented out); replace `sg.popup_error` in `pipeline/hrr_graph.py:plot_line` with a logger call OR raise a typed `ChartPlotError` collected into `warnings: list` on the job. Drop `PySimpleGUI` from `requirements.txt`. Keep `auto_report.py` / `main.py` as reference; never import them. |
| 8 | **Concurrency** | `POST /jobs` while a job is running → `409 Conflict`. Frontend disables the Create Report button while running. Different machines run independently — no shared state. |
| 9 | **Cancellation** | Defer. User closes the app to abort. Revisit if jobs hang in practice. |
| 10 | **Tests** | Characterization tests on the **context dict** (the dict handed to `DocxTemplate.render`). Golden JSON files per fixture. Vendored sample JSONs at repo root are the input fixtures. |
| 11 | **Renderer** | Keep `docxtpl` for MVP. **Builder-pattern migration is a future PR** — see memory `architecture_report_building.md` and obsidian draft `Architecture - Report Building Pattern.md`. The `ctx` discipline below is what protects the cheap switch. |
| 12 | **Post-completion UX** | "Report saved to: <path>" + `[Open in Word]` + `[Reveal in Folder]` buttons. Use `tauri-plugin-shell` (need to add capability scoped to output dir). |
| 13 | **Bare imports fix** | `sys.path.insert(0, str(PIPELINE_DIR))` in `pipeline/server.py` startup, before any pipeline import. Mirrors what `tests/conftest.py` already does. Don't patch every vendored module. |
| 14 | **Frontend errors** | `ValidationError` → inline red text under offending field; `PipelineError` → red banner with `step` + `message`; `InternalError` → red banner with `[Copy diagnostic]` (traceback to clipboard). |
| 15 | **Job state TTL** | In-memory `dict[str, JobState]`, ring buffer of last 10 jobs. Drop oldest. No persistence across sidecar restart. |
| 16 | **File location** | `pipeline/services/report.py` (mirror `backendForNextApp` shape). Future-proofs for more services. |
| 17 | **Logging** | stderr (already inherited by Tauri) + `RotatingFileHandler` writing to `%LOCALAPPDATA%\CFDPostProcessing\logs\sidecar.log`. Tauri passes the dir via new `--log-dir` CLI arg. 5MB × 5 files. |
| 18 | **FastAPI threading** | `asyncio.create_task(asyncio.to_thread(run_orchestrator, state, req))`. Orchestrator is CPU-bound (matplotlib, lxml, PIL); threadpool keeps the polling endpoint responsive. |

## Form inputs (PR 2 keeps legacy parity)

Same 7 fields the legacy `auto_report.run_report` exposed: `PATH`, `CLIENT_NAME`, `PROJECT_NAME`, `PROJECT_LOCATION`, `EMAIL_PREFIX`, `HAS_EXTENDED_TRAVEL`, `MAX_TD`, `GUIDANCE`. Plus the new optional `OUTPUT_DIR` (folder picker, defaults to `PATH`).

Future direction (NOT this PR): replace metadata fields with a job-number input that resolves project info from the company DB. See memory `project_form_inputs_future.md`.

## File layout after PR 2

```
pipeline/
  __init__.py
  server.py                 # FastAPI + sys.path tweak + jobs dict + endpoints
  services/
    __init__.py
    report.py               # NEW: build_context + run_orchestrator
    job.py                  # NEW: JobState dataclass, JobError types
  # vendored modules (untouched by PR 2 except 7):
  scenarios_object.py       # PR 7: kill PSG import
  hrr_graph.py              # PR 7: kill sg.popup_error in plot_line
  ...everything else stays as vendored

src/
  components/
    ReportForm.tsx          # add OUTPUT_DIR picker, polling loop, step/percent UI, error rendering
  lib/
    api.ts                  # add createJob, pollJob, openInWord, revealInFolder

src-tauri/
  capabilities/
    main.json               # add shell:open scoped to output dir
  src/main.rs               # pass --log-dir to sidecar; nothing else changes

tests/
  fixtures/                 # NEW: input run dirs + expected ctx.json per fixture
  test_orchestrator.py      # NEW: parametrized characterization tests
```

## Implementation sequence

Order matters — earlier steps unblock later ones, and you can ship intermediate state.

1. **Strip PSG (Q7)** — small, contained. Confirms the runtime path still works.
2. **`services/job.py`** — define `JobState`, `JobError`, `ErrorType` enum.
3. **`services/report.py` skeleton** — function signature, no body, calls `on_progress` for each phase as a stub. Returns a fake context dict.
4. **`server.py`** — install sys.path tweak, define jobs dict + ring buffer, wire `POST /jobs` + `GET /jobs/{id}` against the stubbed orchestrator. Polling works end-to-end against fake data.
5. **Frontend** — extend `api.ts` with `createJob`/`pollJob`. Update `ReportForm.tsx` to use them, render step+percent. Should now show progress against the stub.
6. **Real orchestrator** — port `main.py`'s logic phase by phase (parse scenarios → charts → draw → render → save). Each phase emits `on_progress`. Read `main.py` for *what data flows*, write fresh code with proper types.
7. **Characterization tests** — pin `ctx` against fixtures. Iterate orchestrator until ctx matches.
8. **Post-completion UX** — Open in Word / Reveal in Folder buttons + Tauri shell plugin.
9. **Logging** — file handler + Tauri `--log-dir` arg.
10. **Polish** — error UI treatments per type, button-disabled-during-run, etc.

## Watch-outs

- **`ctx` shape must be domain-shaped, not template-shaped.** If you find the docxtpl template wants a weird shape, write a tiny `ctx_to_docxtpl(ctx) -> dict` adapter at the rendering boundary. That adapter is what the future builder PR deletes.
- **Hardcoded paths.** Vendored modules look for `Template CFD Report.docx`, `FDAI_grey.png`, `references.csv`, `templates/`, `template/`, `CFD Word Template/` at CWD. Sidecar runs with CWD = project root (already set in `src-tauri/src/main.rs`), so dev works. **PR 3 (PyInstaller bundling) will need to address this** — the bundled exe runs from a temp dir and needs the resources copied alongside.
- **`is_test = True` Easter egg in legacy.** `auto_report.run_report:28-31` hardcodes Ian's Evelyn Court Dropbox path when called as a non-`__main__` import. The new orchestrator MUST NOT carry this over.
- **Vendored modules' subprocess calls.** Some modules use `os.startfile(output_path)` to auto-open Word. Don't carry this over to the orchestrator path — the frontend handles it via the Open in Word button.

## Research-backed migration philosophy

Per Strangler Fig and Feathers' characterization-test approach: don't transcribe `main.py` line-by-line. Read it for understanding, write the new orchestrator fresh, pin behavior with golden tests against the `ctx` dict. Keep legacy in place as a comparison reference until parity is proven on representative fixtures.

## Out of scope for PR 2

- PyInstaller bundling (PR 3)
- Job-number → DB-backed form inputs (future PR; see roadmap memory)
- Builder-pattern renderer migration (future PR; see architecture memory)
- Cancellation
- Multiple concurrent jobs
- Persistent job history across sidecar restarts
- Pushing report-generation events to the company `backendForNextApp` cloud dashboard
