# Release a new desktop version

Hand this to a fresh Claude instance (or follow it yourself). The repo
documents the build mechanics in `BUILD.md` and `PR3_PLAN.md`; this file
is just the trigger sequence.

## Bump

The three version fields must match. Current values live in:

- `package.json` → `"version"`
- `src-tauri/tauri.conf.json` → `"version"`
- `src-tauri/Cargo.toml` → `version = "..."`

Pattern from history: `0.3.0-rc.N` (release candidates), then drop the
`-rc.N` suffix for stable. Confirm with `git log --oneline | head -10`.

## Tag and push

```powershell
git add package.json src-tauri/tauri.conf.json src-tauri/Cargo.toml
git commit -m "vX.Y.Z-rc.N"
git tag vX.Y.Z-rc.N
git push origin main --tags
```

`.github/workflows/release.yml` fires on any `v*` tag. It:

1. Builds the sidecar with PyInstaller (`scripts/build-sidecar.ps1`).
2. Runs `npm run tauri build` to produce the NSIS installer.
3. Creates a GitHub Release with the `.exe` + auto-update artifacts.

Existing app installs pull the update from that Release via the Tauri
updater wired in PR `ec4a1b8`.

## Optional: local smoke before tagging

If the change touches behaviour worth eyeballing, run the dev build
first:

```powershell
npm run dev
```

Click through the flow you care about (e.g. discover → pick scenarios →
Create Report against the Finchley fixture). Tag only once it works.

## If the workflow fails

Read the failing step in the GitHub Actions log. Common causes: version
fields out of sync (the three files above), MSVC linker missing on the
runner (rare — Windows runner has it), Python dep change without a
`requirements.txt` update.
