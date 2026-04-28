# PyInstaller spec for the FastAPI sidecar that the Tauri shell launches.
#
# Build (from project root, with the venv active):
#     pyinstaller --clean --noconfirm pyinstaller-server.spec
#
# Output:
#     dist/pipeline-server/pipeline-server.exe   (Windows)
#
# The Tauri bundler expects this binary under
#     src-tauri/binaries/pipeline-server<target-triple>(.exe)
# at bundle time — wiring that up is a follow-up PR.

# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['pipeline/server.py'],
    pathex=['.', 'pipeline'],
    binaries=[],
    datas=[
        ('templates', 'templates'),
    ],
    hiddenimports=(
        collect_submodules('uvicorn')
        + collect_submodules('fastapi')
        + collect_submodules('pydantic')
    ),
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
    console=True,
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
