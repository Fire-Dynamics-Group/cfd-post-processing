// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpListener;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, RunEvent, State};
use tauri::path::BaseDirectory;

/// Holds the running sidecar process + the port it bound to.
struct SidecarState {
    port: u16,
    child: Mutex<Option<Child>>,
}

/// Reserve an OS-assigned free TCP port on 127.0.0.1, then close the socket so
/// the sidecar can bind to it. There's a tiny TOCTOU window — acceptable for a
/// single-user desktop app.
fn pick_free_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

/// Spawn the Python FastAPI sidecar.
///
/// Dev (debug builds): runs `python -m pipeline.server --port <N>` from the
/// project root (one level above `src-tauri/`).
///
/// Prod (release builds): runs the PyInstaller-produced onedir bundle
/// shipped via Tauri's `bundle.resources`. The exe lives at
/// `<Resource>/pipeline-server-x86_64-pc-windows-msvc/pipeline-server.exe`;
/// CWD is set to that directory so the sidecar's `os.chdir(_MEIPASS)` and
/// the legacy relative-path lookups (e.g. `'SEGOEUIL.TTF'`) resolve.
///
/// `log_dir` is forwarded as `--log-dir` so the sidecar writes a rotating
/// `sidecar.log` for post-mortem debugging on user machines.
fn spawn_sidecar(
    app: &AppHandle,
    port: u16,
    log_dir: &std::path::Path,
) -> Result<Child, String> {
    let log_dir_str = log_dir.to_string_lossy().into_owned();

    if cfg!(debug_assertions) {
        // Project root = parent of src-tauri/
        let manifest_dir = env!("CARGO_MANIFEST_DIR");
        let project_root = std::path::Path::new(manifest_dir)
            .parent()
            .ok_or_else(|| "could not resolve project root".to_string())?
            .to_path_buf();

        // Prefer the venv interpreter if it exists, else fall back to PATH.
        let venv_python = project_root.join("venv").join("Scripts").join("python.exe");
        let python_cmd = if venv_python.exists() {
            venv_python.to_string_lossy().into_owned()
        } else {
            "python".to_string()
        };

        return Command::new(python_cmd)
            .args([
                "-m",
                "pipeline.server",
                "--port",
                &port.to_string(),
                "--log-dir",
                &log_dir_str,
            ])
            .current_dir(&project_root)
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|e| format!("failed to spawn dev sidecar: {e}"));
    }

    // Production: locate the bundled sidecar exe. Tauri's resource glob
    // handling can map `binaries/<dir>/**/*` to either `<Resource>/<dir>/...`
    // or `<Resource>/...` depending on how the base is computed; probe a
    // small set of candidates rather than commit to one and break the
    // installer if the convention shifts between versions.
    let candidate_relative_paths = [
        "binaries/pipeline-server-x86_64-pc-windows-msvc/pipeline-server.exe",
        "pipeline-server-x86_64-pc-windows-msvc/pipeline-server.exe",
        "pipeline-server.exe",
    ];
    let resolver = app.path();
    let sidecar_exe = candidate_relative_paths
        .iter()
        .filter_map(|rel| resolver.resolve(rel, BaseDirectory::Resource).ok())
        .find(|p| p.exists())
        .ok_or_else(|| {
            format!(
                "Could not locate bundled sidecar in Resource dir. Tried: {}",
                candidate_relative_paths.join(", ")
            )
        })?;

    let sidecar_dir = sidecar_exe
        .parent()
        .ok_or_else(|| "no parent for sidecar exe".to_string())?
        .to_path_buf();

    Command::new(&sidecar_exe)
        .args(["--port", &port.to_string(), "--log-dir", &log_dir_str])
        .current_dir(&sidecar_dir)
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|e| format!("failed to spawn release sidecar: {e}"))
}

/// Block until `GET http://127.0.0.1:<port>/health` returns HTTP 200, or until
/// the timeout elapses.
fn wait_for_health(port: u16, timeout: Duration) -> Result<(), String> {
    let url = format!("http://127.0.0.1:{port}/health");
    let deadline = Instant::now() + timeout;
    let mut last_err = String::from("not ready");

    while Instant::now() < deadline {
        match ureq::get(&url).timeout(Duration::from_millis(500)).call() {
            Ok(resp) if resp.status() == 200 => return Ok(()),
            Ok(resp) => {
                last_err = format!("status {}", resp.status());
            }
            Err(e) => {
                last_err = e.to_string();
            }
        }
        thread::sleep(Duration::from_millis(200));
    }
    Err(format!("sidecar /health never went green: {last_err}"))
}

#[tauri::command]
fn get_sidecar_port(state: State<SidecarState>) -> u16 {
    state.port
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let port = pick_free_port().map_err(|e| format!("pick_free_port: {e}"))?;
            println!("[tauri] picked sidecar port: {port}");

            // %LOCALAPPDATA%\CFDPostProcessing\logs on Windows.
            let log_dir = app
                .path()
                .resolve("CFDPostProcessing/logs", BaseDirectory::LocalData)
                .map_err(|e| format!("resolve log_dir: {e}"))?;
            std::fs::create_dir_all(&log_dir)
                .map_err(|e| format!("create_dir_all log_dir: {e}"))?;
            println!("[tauri] sidecar log_dir: {}", log_dir.display());

            let child = spawn_sidecar(app.handle(), port, &log_dir)?;
            println!("[tauri] sidecar spawned (pid {})", child.id());

            // Don't fail startup if /health is slow on first boot — surface
            // the error to logs but let the UI come up so the user can see
            // a meaningful message in the form's status area.
            if let Err(err) = wait_for_health(port, Duration::from_secs(30)) {
                eprintln!("[tauri] WARNING: {err}");
            } else {
                println!("[tauri] sidecar /health is alive");
            }

            app.manage(SidecarState {
                port,
                child: Mutex::new(Some(child)),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_sidecar_port])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(state) = app_handle.try_state::<SidecarState>() {
                    if let Ok(mut guard) = state.child.lock() {
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                            let _ = child.wait();
                            println!("[tauri] sidecar killed");
                        }
                    }
                }
            }
        });
}
