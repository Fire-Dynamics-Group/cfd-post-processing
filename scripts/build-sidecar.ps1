<#
.SYNOPSIS
    Build the FastAPI sidecar with PyInstaller and stage it for Tauri.

.DESCRIPTION
    1. Activates the project venv.
    2. Runs `pyinstaller --clean --noconfirm pyinstaller-server.spec`,
       producing dist/pipeline-server/ (onedir layout).
    3. Replaces src-tauri/binaries/pipeline-server-x86_64-pc-windows-msvc/
       with the freshly built tree, where Tauri's bundle.resources picks
       it up at `npm run tauri build` time.

    Run this BEFORE `npm run tauri build`. See BUILD.md for the full runbook.

.NOTES
    Windows-only, by design — Tauri builds for the host triple, and the
    sidecar's PyInstaller output is platform-specific. Cross-platform is
    out of scope for PR 3 (decision #6, decision #11).
#>

# Avoid `$ErrorActionPreference = 'Stop'` because pyinstaller writes
# normal progress output to stderr; PowerShell 5.1 would otherwise
# treat each line as a terminating error and abort the script. Use
# explicit $LASTEXITCODE / Test-Path checks instead.

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $repoRoot

$venvActivate = Join-Path $repoRoot 'venv\Scripts\Activate.ps1'
if (-not (Test-Path $venvActivate)) {
    Write-Error "venv not found at $venvActivate. Create it with: python -m venv venv && venv\Scripts\pip install -r requirements.txt"
    exit 1
}
& $venvActivate

Write-Host '==> Running PyInstaller (this takes ~60-120s) ...' -ForegroundColor Cyan
pyinstaller --clean --noconfirm pyinstaller-server.spec
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

$distDir = Join-Path $repoRoot 'dist\pipeline-server'
$exePath = Join-Path $distDir 'pipeline-server.exe'
if (-not (Test-Path $exePath)) {
    Write-Error "Expected sidecar exe not found at $exePath"
    exit 1
}

# Tauri target-triple naming convention — keeps us consistent with
# externalBin / sidecar examples in the wild even though we're shipping
# the directory via bundle.resources, not externalBin.
$targetTriple = 'x86_64-pc-windows-msvc'
$stagingDir = Join-Path $repoRoot "src-tauri\binaries\pipeline-server-$targetTriple"

Write-Host "==> Staging build artefacts to $stagingDir ..." -ForegroundColor Cyan
if (Test-Path $stagingDir) {
    Remove-Item -Recurse -Force $stagingDir -Confirm:$false
}
New-Item -ItemType Directory -Path $stagingDir -Force | Out-Null
Copy-Item -Recurse -Path (Join-Path $distDir '*') -Destination $stagingDir -Force
if (-not $?) {
    Write-Error "Failed to stage sidecar build artefacts"
    exit 1
}

Write-Host "==> Sidecar staged. Next: npm run tauri build" -ForegroundColor Green
