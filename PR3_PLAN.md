# PR 3 Plan — Bundle the desktop app for distribution

> Hand-off doc. Drafted with sensible defaults, then revised against
> 2025–2026 production-Tauri-with-Python-sidecar best practice.
> Read end-to-end before touching code; the recommendations chain
> together. Sources at the bottom.

## Goal

Make the desktop app installable as a single `.exe` on a teammate's
Windows machine **without** any dev tooling (no Python venv, no Node, no
Rust, no VS Code). They double-click the installer, click through, run
"CFD Post-Processing" from the Start menu, generate a report against a
real run dir, and open the resulting `.docx` in Word.

PR 2 produced a working app that runs in `npm run tauri dev` only. PR 3
turns that into a redistributable Windows installer.

## Starting state (after PR 2 commits 208c3ab → 612c431)

- `pipeline/server.py` is the FastAPI sidecar entry-point. Accepts
  `--port` and `--log-dir`. Real CFD orchestrator works end-to-end —
  proven by `tests/test_orchestrator_e2e.py` (49s against the Finchley
  Rev00 Models dir).
- `src-tauri/src/main.rs` already has the **release-mode spawn path**
  declared, but its current form expects
  `<exe_dir>/binaries/pipeline-server.exe`. PR 3 will need to change
  this — see decision #3.
- `pyinstaller-server.spec` exists at repo root. Crucially it is
  **already a `--onedir` spec** (uses `EXE(... exclude_binaries=True)`
  + `COLLECT(...)`). It only collects `uvicorn`/`fastapi`/`pydantic`
  submodules and one `templates/` data entry — needs major extension.
- `src-tauri/tauri.conf.json` has `bundle.resources: ["../templates/*"]`
  but does not declare any sidecar wiring yet.
- The Python orchestrator's resource lookup
  (`_resolve_template_path()`, `_resolve_references_csv()`) currently
  falls back to CWD or the parent of `pipeline/`; **neither matches
  the bundled layout**. Decision #2 fixes this.

## Architecture decisions (locked)

### Headline calls

| # | Topic | Decision |
|---|---|---|
| 1 | **PyInstaller mode** | `--onedir`. The existing spec already does this. ~250 MB extracted footprint, but cold-start is ~1 s (vs 5–15 s for `--onefile` on this stack with matplotlib + fdsreader + cv2 + lxml + reportlab + fitz, especially with Defender scanning `%TEMP%\_MEIxxxx`). Onedir also sidesteps the `--onefile` two-process shutdown bug ([Tauri #11686](https://github.com/tauri-apps/tauri/issues/11686)) where Tauri sees only the bootloader pid and orphans the Python child. |
| 2 | **Resource bundling** | PyInstaller `datas` is the **single source of truth**. Do NOT also ship resources via Tauri `bundle.resources` — they'd land at a different path (`$RESOURCES`, not next to `sys.executable`) and the sidecar can't reach them without IPC plumbing the Tauri docs explicitly call out. Lookup order in Python: `sys._MEIPASS` (set inside PyInstaller bundles) → `Path(sys.executable).parent` → dev fallback `Path(__file__).resolve().parents[2]`. |
| 3 | **Sidecar wiring (NOT externalBin)** | Ship the **entire** `dist/pipeline-server/` directory (the PyInstaller onedir output) via Tauri's resource mechanism, NOT `bundle.externalBin` — externalBin is for single files. Update `main.rs:spawn_sidecar` to resolve the inner exe via `app.path().resolve("pipeline-server/pipeline-server.exe", BaseDirectory::Resource)`. The current `<exe_dir>/binaries/pipeline-server.exe` path is wrong for either externalBin or resources and must be replaced. |
| 4 | **Hidden imports / data files** | The vendored `pipeline/*.py` modules use bare imports (`from helper_functions import ...`). Spec sets `pathex=['.', 'pipeline']` (already correct) and adds `collect_submodules` for everything PyInstaller hooks-contrib doesn't cover. Confirmed via 2026 hooks-contrib coverage: `matplotlib`, `pandas`, `numpy`, `lxml`, `PIL`, `cv2`, `uvicorn`, `reportlab` ship hooks; **`fdsreader`, `docxtpl`, `fitz` (PyMuPDF) do not** and need explicit `collect_submodules` entries. |
| 5 | **Vendored-module discovery in bundle** | `pipeline/server.py` already does `sys.path.insert(0, _PIPELINE_DIR)` using `os.path.dirname(__file__)`. In PyInstaller onedir, `__file__` resolves to inside the bundle's `_internal/` (or whatever the bootloader extracts to), and PyInstaller flattens the import graph anyway — so the vendored modules just need to be in the spec's `pathex` (already done) for the analyzer to find them. Verify on first build. |
| 6 | **Installer format** | NSIS (`.exe`) — Tauri's default Windows target. Smaller than MSI, no admin rights to install. MSI is a follow-up if the team needs Group Policy deployment. |
| 7 | **Code signing** | **Skip — indefinitely.** Internal-tool distribution via Dropbox or a shared drive doesn't need it. The "Mark of the Web" attribute that triggers SmartScreen warnings is set by browsers, not by file copies; UNC-path copies and Dropbox-synced files are warning-free. If someone *does* download via a browser, the warning is one click ("More info" → "Run anyway") and never appears again on that machine. Revisit only if (a) we ever distribute outside the team, (b) we wire `tauri-plugin-updater` (which needs signing for the auto-update flow), or (c) corporate policy mandates signed binaries. None apply today. |
| 8 | **Auto-update** | Defer. No `tauri-plugin-updater`, no signed update manifest. New version = re-run installer. *Trap to know about for the future:* the ed25519 private key used to sign updates is unrecoverable; losing it forces every user to manually reinstall. Store in password manager + at least one off-machine backup before any signed release. |
| 9 | **Distribution channel** | PR 3: build locally, drop the `.exe` on the team Dropbox. CI workflow is a stretch goal — see step 11. |
| 10 | **Versioning** | Bump `package.json`, `Cargo.toml`, `tauri.conf.json` from 0.1.0 → 0.2.0. Single source of truth: keep aligned manually for now, automate later. |
| 11 | **CI** | **Stretch goal.** [`tauri-apps/tauri-action`](https://github.com/tauri-apps/tauri-action) is the canonical pattern. ~40 lines of YAML; trigger on tag push; runs on `windows-latest`; `actions/setup-python@v5` → `pip install pyinstaller -r requirements.txt` → build script → `tauri-action` with `includeUpdaterJson: false`. Defer if it inflates PR 3 scope. |
| 12 | **Smoke test gate** | Manual: install on a clean Windows account that has never had Python, run, generate a report against the Finchley dir, verify the `.docx` opens in Word. Document in `BUILD.md`. |
| 13 | **WebView2** | Tauri's default config bundles the WebView2 evergreen bootstrapper. Most Win11 has it. Default is fine. |
| 14 | **Logs in production** | Same path as dev: `%LOCALAPPDATA%\CFDPostProcessing\logs\sidecar.log`. Already wired in `main.rs` via `BaseDirectory::LocalData`; works identically in bundled mode. |
| 15 | **Console window on launch** | Spec currently has `console=True`. Bundled mode should be `console=False` so no flashing console window. Sidecar's stdout/stderr are inherited by Tauri anyway, and file logging covers post-mortem. |
| 16 | **Build invocation** | Two-stage: (a) `pyinstaller --clean --noconfirm pyinstaller-server.spec` → `dist/pipeline-server/` (directory); (b) `npm run tauri build` produces the NSIS installer, with Tauri picking up the directory as a resource. Glue the copy/path step into `scripts/build-sidecar.ps1` (PowerShell, since this is Windows-only). |
| 17 | **Cold-start optimization (NEW)** | Lazy-import the heavy scientific stack inside route/orchestrator function bodies, not at module top. `matplotlib` alone is ~70% of import cost on this kind of app; `fdsreader` + `pandas` + `lxml` add another 1–3 s. Top-level imports stay limited to `fastapi`, `uvicorn`, `pydantic`, `dataclasses`. Heavy imports (`matplotlib`, `fdsreader`, `lxml`, `docx`, `docxtpl`, `cv2`, `fitz`, `reportlab`) move inside `pipeline/services/report.py:run_orchestrator` and the helpers it calls. Buys 2–4 s of perceived startup at zero risk. |
| 18 | **Tauri 2 capability for the sidecar** | Tauri 2 capabilities are mandatory and granular. Even with sidecar wired through `bundle.resources` rather than `externalBin`, the spawn happens via `std::process::Command` from `main.rs` (not `tauri-plugin-shell`), so no extra capability is required for the spawn itself. Capabilities only need updating if we ever switch to `tauri-plugin-shell::sidecar` API. |

### Why these specific deviations from a naive plan

- **Onedir over onefile** — the agent research found 5–10 s cold-start for this stack with `--onefile` on Defender-active machines, and the [Tauri #11686 shutdown bug](https://github.com/tauri-apps/tauri/issues/11686) is a real footgun (orphaned Python processes after app close). Onedir solves both for the cost of ~250 MB of disk vs ~150 MB.
- **Single-source-of-truth resources** — duplicating templates/fonts in both PyInstaller datas and Tauri resources doubles the installer size for no benefit, since the sidecar can't reach Tauri-resolved paths without IPC.
- **Lazy imports** — costs nothing, saves seconds on every cold start. The first job already takes 50 s, so the user won't notice the first-import lag fold into that.

## File layout after PR 3

```
src-tauri/
  binaries/                                # NEW: produced by build-sidecar.ps1
    pipeline-server-x86_64-pc-windows-msvc/      # (onedir output, copied from dist/)
      pipeline-server.exe
      _internal/                                  # PyInstaller's runtime support tree
        ...
  tauri.conf.json                          # bundle.resources points to the dir
  src/main.rs                              # spawn path resolves via Resource dir

pyinstaller-server.spec                    # Audited, extended hidden imports + datas
BUILD.md                                   # NEW: build + smoke-test runbook
scripts/
  build-sidecar.ps1                        # NEW: pyinstaller + copy-to-binaries
.github/                                   # OPTIONAL stretch goal
  workflows/
    release.yml                            # tag push → windows-latest build → Release

# unchanged from PR 2:
pipeline/services/report.py                # tiny edits: lazy-imports + sys._MEIPASS lookup
```

`.gitignore`: add `src-tauri/binaries/` (build artifact, not source).

## Implementation sequence

1. **Audit `pyinstaller-server.spec`** — confirm onedir layout, list missing
   hidden imports / datas / `console=True` flag.

2. **Extend the spec for full bundle coverage**
   - Hidden imports: `collect_submodules('fdsreader')`, `collect_submodules('docxtpl')`, plus `'fitz'`, plus `uvicorn` lifecycle hooks (`uvicorn.logging`, `uvicorn.loops.auto`, `uvicorn.protocols.http.auto`, `uvicorn.protocols.websockets.auto`, `uvicorn.lifespan.on`) — uvicorn's hook misses these on some setups.
   - `collect_data_files('docxtpl')` — ships its internal Jinja templates.
   - `collect_data_files('matplotlib')` — covers backend resources.
   - `datas`: every `pipeline/*.py` (vendored modules), `template/`, `templates/`, `CFD Word Template/`, fonts (`SEGOEUIL.TTF`, `Segoe UI Light.ttf`), `references.csv`, `FDAI_grey.png`, `Template CFD Report.docx`.
   - `console=False`.
   - Keep the existing `EXE(... exclude_binaries=True)` + `COLLECT(...)` blocks (they produce onedir).

3. **Add lazy imports + `sys._MEIPASS` lookup to the orchestrator**
   - Move `import matplotlib`, `from hrr_graph import ...`, `from report_draw import ...`, `from docx import ...`, `from docxtpl import ...` etc. from `pipeline/services/report.py` module-top into the function bodies that use them.
   - Keep `from .job import Step` and pydantic at top.
   - Update `_resolve_template_path()` and `_resolve_references_csv()` to walk: `sys._MEIPASS` (if set) → `Path(sys.executable).parent` → existing dev fallback. Add a unit test that monkeypatches `sys.executable` to a tmp_path with the resource present.

4. **Build the sidecar**
   ```powershell
   venv\Scripts\Activate.ps1
   pyinstaller --clean --noconfirm pyinstaller-server.spec
   ```
   Verify `dist/pipeline-server/pipeline-server.exe` exists and the `_internal/` sibling directory is populated.

5. **Standalone sidecar smoke test** — *before* touching Tauri.
   - From `dist/pipeline-server/`: `.\pipeline-server.exe --port 9999 --log-dir tmp_logs`
   - `curl http://127.0.0.1:9999/health` → `{"status":"alive"}`
   - POST a job against the Finchley dir → poll → expect `completed` with `output_path` set and a real `.docx` on disk
   - On any `ModuleNotFoundError` or missing-resource error: extend the spec, rebuild, retry. Loop until green. **Do not move on until this works** — debugging PyInstaller through `npm run tauri build`'s 3-minute pipeline is miserable.

6. **`scripts/build-sidecar.ps1`**
   - Activates the venv, runs PyInstaller, copies `dist/pipeline-server/` to `src-tauri/binaries/pipeline-server-x86_64-pc-windows-msvc/` (preserving the inner directory structure).

7. **Wire Tauri to ship + spawn the directory**
   - `src-tauri/tauri.conf.json`:
     ```json
     "bundle": {
       "active": true,
       "targets": "nsis",
       "resources": [
         "binaries/pipeline-server-x86_64-pc-windows-msvc/**/*"
       ]
     }
     ```
   - `src-tauri/src/main.rs`: replace the `exe_dir.join("binaries").join("pipeline-server")` lookup with `app.path().resolve("pipeline-server-x86_64-pc-windows-msvc/pipeline-server.exe", BaseDirectory::Resource)`. Same `--port` + `--log-dir` args as today.

8. **`npm run tauri build`** — produces `src-tauri/target/release/bundle/nsis/CFD Post-Processing_0.2.0_x64-setup.exe`.

9. **Clean-machine smoke test** — install on a Windows account that has never had Python; launch from Start menu; generate a report against the Finchley dir; click Open in Word. Document any failures and loop.

10. **Write `BUILD.md`** — runbook covering: dev prereqs, two-step build (`scripts/build-sidecar.ps1` then `npm run tauri build`), smoke-test procedure, where the installer lands, internal distribution.

11. **(STRETCH) `.github/workflows/release.yml`** — `windows-latest`, tag-push trigger, setup Python+Node+Rust, run build script, call `tauri-action` with `includeUpdaterJson: false`, attach `.exe` to GitHub Release. Skip if it inflates scope.

## Watch-outs

- **Two-process shutdown gotcha** ([Tauri #11686](https://github.com/tauri-apps/tauri/issues/11686)) — only matters in `--onefile` mode. We're on `--onedir` per decision #1, so this should be a non-issue. *If* you ever revert to onefile, implement stdin-EOF-driven shutdown in `pipeline/server.py` (read EOF on stdin → graceful exit), or use `command.group_spawn()` so the whole process group dies with the bootloader.
- **`pyinstaller-hooks-contrib` does NOT ship hooks for `fdsreader`, `docxtpl`, or full `fitz`/PyMuPDF.** That's why the spec adds explicit `collect_submodules` for them. Re-confirm on each new PyInstaller release; if hooks land upstream, the manual entries become redundant but harmless.
- **`matplotlib` backends.** PyInstaller bundles only the backend matplotlib detects at build time. Force `Agg` at the top of `pipeline/services/report.py` before the lazy import block:
  ```python
  os.environ.setdefault("MPLBACKEND", "Agg")
  ```
  Without this, the bundled app may try to load Tk/Qt and fail on a machine without those.
- **`docxtpl` Jinja templates.** Use `collect_data_files('docxtpl')` (decision #4 covers this). Without it, rendering crashes with template-not-found errors only at runtime.
- **`%MEIPASS%` runtime path.** PyInstaller exposes `sys._MEIPASS` inside both onefile (per-run extraction dir) and onedir (the `_internal/` subdir, in newer PyInstaller). The orchestrator's resource lookup checks `sys._MEIPASS` *first* per decision #2.
- **Long path support.** `%LOCALAPPDATA%\CFDPostProcessing\logs\sidecar.log` is fine. Onedir avoids the deep `_MEIxxxx` paths that onefile would create. If long paths bite anyway, document Windows long-path policy in `BUILD.md`.
- **Antivirus / SmartScreen.** Unsigned `.exe`s built with PyInstaller trip Defender SmartScreen *only when the file has the Mark-of-the-Web attribute* (i.e. downloaded via browser). Distribute via Dropbox sync or UNC share and there's no warning at all. If a browser download is unavoidable, the user clicks "More info" → "Run anyway" once. PyInstaller bundles also occasionally trigger AV false positives on the bootloader exe; if it bites, file with the AV vendor — usually whitelisted in days. No code-signing dependency.
- **`.gitignore` for `src-tauri/binaries/`.** It's a build artifact, not source. Add to `.gitignore` in step 6.
- **Tauri 2 capability for spawn.** We spawn via `std::process::Command` directly from `main.rs` (not `tauri-plugin-shell`), so no `shell:allow-execute` capability is needed. If a future change moves spawning into the JS frontend via `tauri-plugin-shell`, that capability would have to be added.

## Test plan

- **Existing tests must remain green.**
  - `pytest tests/` — 82 fast tests in ~2 s.
  - `pytest -m slow tests/` — 4 slow tests in ~50 s (e2e + spawn smoke + log-dir).
  - `npm test` — 25 frontend tests in ~3 s.
  - `tsc --noEmit` clean. `cargo check` clean.
- **New for PR 3.**
  - Unit test for `sys._MEIPASS` / `Path(sys.executable).parent` resource lookup (monkeypatch `sys.executable` to a tmp_path with the resource present).
  - Unit test that the orchestrator's lazy imports actually defer (e.g. `import pipeline.services.report` followed by `assert "matplotlib" not in sys.modules`).
  - Manual: standalone sidecar smoke test (step 5).
  - Manual: clean-machine install + report generation (step 9).

## Production repos to learn from

When the implementation hits a wiring detail this plan doesn't pin, copy from these — they ship the same architecture (Tauri 2 + FastAPI + PyInstaller) and have already paid the costs:

- **[dieharders/example-tauri-v2-python-server-sidecar](https://github.com/dieharders/example-tauri-v2-python-server-sidecar)** — closest match. Read their `main.rs` for the spawn/shutdown dance.
- **[AlanSynn/vue-tauri-fastapi-sidecar-template](https://github.com/AlanSynn/vue-tauri-fastapi-sidecar-template)** — clean target-triple naming convention, separate `build:sidecar-winos` script that mirrors what we'll have.
- **[Building Production-Ready Desktop LLM Apps](https://aiechoes.substack.com/p/building-production-ready-desktop)** (writeup, not a repo) — the most thorough catalogue of PyInstaller spec gotchas for native-binary-loading deps. Their llama.cpp DLL issues map well to our `fdsreader` / `cv2` / `fitz` natives.

## Out of scope for PR 3

- Code signing — and not deferred to a later PR either; only revisit if external distribution / auto-updates / corporate policy ever demand it.
- `tauri-plugin-updater` auto-updates.
- Cross-platform installers (macOS / Linux) — Windows-only for now.
- Builder-pattern renderer migration (still future PR).
- Job-number → DB-backed form inputs (future PR).
- CI release pipeline if step 11 proves too costly — defer to PR 4.

## Sources

- [Tauri 2 sidecar docs](https://v2.tauri.app/develop/sidecar/)
- [Tauri 2 resources docs](https://v2.tauri.app/develop/resources/)
- [Tauri sidecar shutdown bug #11686](https://github.com/tauri-apps/tauri/issues/11686)
- [PyInstaller runtime info / `_MEIPASS`](https://pyinstaller.org/en/stable/runtime-information.html)
- [pyinstaller-hooks-contrib](https://github.com/pyinstaller/pyinstaller-hooks-contrib)
- [Nuitka vs PyInstaller comparison](https://krrt7.dev/en/blog/nuitka-vs-pyinstaller)
- [Authenticode in 2025 — Azure Trusted Signing](https://textslashplain.com/2025/03/12/authenticode-in-2025-azure-trusted-signing/)
- [Tauri updater plugin docs](https://v2.tauri.app/plugin/updater/)
- [tauri-action GitHub Action](https://github.com/tauri-apps/tauri-action)
- [Building Production-Ready Desktop LLM Apps](https://aiechoes.substack.com/p/building-production-ready-desktop)
