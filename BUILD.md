# Build & distribute the CFD Post-Processing desktop app

Runbook for producing a Windows `.exe` installer that a teammate can run
on a clean machine — no Python, Node, Rust, or VS Code required. PR 3
introduced this workflow; the architectural decisions live in
[PR3_PLAN.md](./PR3_PLAN.md).

## One-time dev prerequisites

On the build machine (Windows 10 or 11):

- **Python 3.10** with the project's `venv` populated
  ```powershell
  python -m venv venv
  venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```
- **Node.js 18+** and project dependencies
  ```powershell
  npm install
  ```
- **Rust toolchain** with the Tauri build tooling
  ```powershell
  rustup default stable
  cargo install tauri-cli --version "^2"
  ```
- **Visual Studio Build Tools 2022** with the "Desktop development with
  C++" workload (provides the MSVC linker that Tauri's release build
  needs).

## Two-step build

### Step 1 — bundle the sidecar

```powershell
.\scripts\build-sidecar.ps1
```

This:

1. Activates the venv.
2. Runs `pyinstaller --clean --noconfirm pyinstaller-server.spec`,
   producing `dist/pipeline-server/pipeline-server.exe` plus the
   `_internal/` runtime tree (onedir layout — see PR 3 decision #1 for
   why not onefile).
3. Copies the whole tree into
   `src-tauri/binaries/pipeline-server-x86_64-pc-windows-msvc/`, which
   `tauri.conf.json` references as a bundle resource.

Expect ~60–120 s on first run. Output footprint: ~250 MB (the sidecar
ships its own Python interpreter + the scientific stack).

### Step 1.5 — standalone sidecar smoke test (recommended)

Before chasing PyInstaller bugs through the Tauri build, prove the
bundled sidecar actually works:

```powershell
cd dist\pipeline-server
.\pipeline-server.exe --port 9999 --log-dir tmp_logs
```

In another terminal:

```powershell
curl http://127.0.0.1:9999/health
# -> {"status":"alive"}

# Optional: kick a real job against the Finchley Rev00 Models dir.
$body = @{
  PATH          = 'C:\path\to\Finchley\Rev00 Models'
  CLIENT_NAME   = 'Smoke Test'
  PROJECT_NAME  = 'Finchley'
  PROJECT_LOCATION = 'London'
  EMAIL_PREFIX  = 'someone'
  HAS_EXTENDED_TRAVEL = $true
  GUIDANCE      = 'BS9991'
} | ConvertTo-Json
$job = (Invoke-RestMethod -Method POST -Uri http://127.0.0.1:9999/jobs -Body $body -ContentType 'application/json')
# Poll Invoke-RestMethod -Uri "http://127.0.0.1:9999/jobs/$($job.job_id)"
# Expect status -> completed and output_path -> a real .docx
```

If anything fails with `ModuleNotFoundError`, missing-resource, or
"backend not found", extend `pyinstaller-server.spec` (hidden imports /
datas), rebuild, and retry. Debugging through `npm run tauri build`'s
3-minute pipeline is far more painful than rerunning step 1.

### Step 2 — build the installer

```powershell
npm run tauri build
```

Output:

```
src-tauri/target/release/bundle/nsis/CFD Post-Processing_0.2.0_x64-setup.exe
```

That single file is what you distribute.

## Smoke-testing the installer on a clean machine

PR 3 acceptance gate: the installer must run on a Windows account that
has never had Python.

1. Copy the `.exe` to a fresh Windows VM (or a teammate's machine that
   has never built this project).
2. Double-click → click through the NSIS installer (defaults are fine).
3. Launch "CFD Post-Processing" from the Start menu.
4. Generate a report against the Finchley Rev00 Models dir.
5. Click "Open in Word" — confirm the `.docx` opens cleanly.

If SmartScreen warns ("Windows protected your PC"), click **More info →
Run anyway**. This warning only appears for files downloaded via a
browser (Mark-of-the-Web) — installers shared via Dropbox sync or UNC
share won't trigger it. We are deliberately not code-signing (PR 3
decision #7); revisit only if external distribution or auto-update ever
becomes a requirement.

## Distribution

Internal-only for now: drop the `.exe` in the team Dropbox / shared
drive and ping the channel.

A GitHub Actions release pipeline is sketched as a stretch goal in the
plan (`PR3_PLAN.md` step 11) but deferred unless the manual workflow
becomes a bottleneck.

## Versioning

Three places, kept aligned manually:

- `package.json` → `version`
- `src-tauri/Cargo.toml` → `[package].version`
- `src-tauri/tauri.conf.json` → `version`

Bump all three together. The installer filename embeds the
`tauri.conf.json` value.

## Troubleshooting

- **`pyinstaller` exits with `ModuleNotFoundError` at runtime.** Add the
  missing module to `hiddenimports` in `pyinstaller-server.spec`. If
  the module ships data files (Jinja templates, mpl-data, etc.), also
  add `collect_data_files('thatmodule')` to `datas`.
- **Sidecar can't find `'SEGOEUIL.TTF'` / `'Template CFD Report.docx'`
  / `references.csv`.** The bundle is missing the file. Add to `datas`
  in the spec with `dest='.'`. The orchestrator's `_resolve_resource`
  finds them via `sys._MEIPASS`; legacy modules with relative-path
  `open()` calls find them via the `os.chdir(_MEIPASS)` at the top of
  `pipeline/server.py`.
- **`cargo check` (or `npm run tauri build`) errors with
  `glob pattern binaries/... path not found`.** You haven't run
  `scripts/build-sidecar.ps1` yet. The Tauri build script verifies that
  resource globs match real files — running the sidecar build first is
  required.
- **The Tauri spawn says "Could not locate bundled sidecar in Resource
  dir."** Tauri's resource glob copied the directory differently than
  expected. The Rust side probes three candidate paths
  (`binaries/<triple>/...`, `<triple>/...`, root); if none match,
  inspect the installed `resources/` folder manually
  (`%LOCALAPPDATA%\Programs\CFD Post-Processing\resources\...`) and
  add the actual path as a fourth candidate in
  `src-tauri/src/main.rs:spawn_sidecar`.
- **Sidecar logs.** `%LOCALAPPDATA%\CFDPostProcessing\logs\sidecar.log`
  — rotating, 5 MB × 5 files. Same path in dev and prod.
