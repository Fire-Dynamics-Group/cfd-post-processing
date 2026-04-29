# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the FastAPI sidecar that the Tauri shell launches.

Build (from project root, with the venv active):
    pyinstaller --clean --noconfirm pyinstaller-server.spec

Output (Windows, onedir layout — PR 3 decision #1):
    dist/pipeline-server/pipeline-server.exe
    dist/pipeline-server/_internal/   <-- data files + Python runtime

`scripts/build-sidecar.ps1` then copies the whole dist/pipeline-server/ tree
into src-tauri/binaries/pipeline-server-x86_64-pc-windows-msvc/, where
Tauri picks it up via bundle.resources (PR 3 decision #3).

PR 3 decision #4: pyinstaller-hooks-contrib (2023.9) does NOT ship hooks
for fdsreader, docxtpl, or full PyMuPDF (fitz). Explicit
collect_submodules / hidden imports below cover them. matplotlib,
uvicorn, fastapi, pydantic, numpy, pandas, lxml, PIL, cv2, reportlab DO
ship hooks via pyinstaller-hooks-contrib.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Modules pulled in dynamically that the static analyser can't see.
hidden_imports = (
    collect_submodules('uvicorn')
    + collect_submodules('fastapi')
    + collect_submodules('pydantic')
    + collect_submodules('fdsreader')
    + collect_submodules('docxtpl')
    + collect_submodules('docx')
    + [
        'fitz',
        # uvicorn lifecycle hooks miss on some setups even with
        # collect_submodules; explicit picks avoid surprise ImportErrors.
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.on',
    ]
)

# Data files — (source, dest_dir). dest='.' lands the file at the
# MEIPASS root, where the orchestrator's _resolve_resource and the
# os.chdir(MEIPASS) at server.py:top expect them.
datas = [
    ('Template CFD Report.docx', '.'),
    ('references.csv', '.'),
    ('SEGOEUIL.TTF', '.'),
    ('Segoe UI Light.ttf', '.'),
    ('FDAI_grey.png', '.'),
    # Whole-directory bundling for the slice/PDF templates and the
    # legacy CFD Word Template tree. The current orchestrator does not
    # touch these, but bundling them is cheap insurance for future
    # report-mode additions and avoids a rebuild dance later.
    ('templates', 'templates'),
    ('template', 'template'),
    ('CFD Word Template', 'CFD Word Template'),
]

# docxtpl ships internal Jinja templates; matplotlib needs its mpl-data
# tree at runtime (font caches, sample style sheets).
datas += collect_data_files('docxtpl')
datas += collect_data_files('matplotlib')

a = Analysis(
    ['pipeline/server.py'],
    # `.` lets the analyser find `pipeline.server`; `pipeline` makes the
    # bare-import vendored modules (`from helper_functions import ...`)
    # discoverable. (Decision #5.)
    pathex=['.', 'pipeline'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='pipeline-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # No flashing console window in production (decision #15). The
    # sidecar's stdout/stderr are inherited by Tauri anyway, and file
    # logging covers post-mortem debugging.
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='pipeline-server',
)
