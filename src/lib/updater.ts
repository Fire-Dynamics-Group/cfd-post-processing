import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { ask, message } from "@tauri-apps/plugin-dialog";
import { invoke } from "@tauri-apps/api/core";

export async function checkForUpdates(opts: { silent?: boolean } = {}) {
  const { silent = false } = opts;

  let update;
  try {
    update = await check();
  } catch (err) {
    if (!silent) {
      await message(`Update check failed: ${err}`, {
        title: "CFD Post-Processing",
        kind: "error",
      });
    }
    return;
  }

  if (!update) {
    if (!silent) {
      await message("You're on the latest version.", {
        title: "CFD Post-Processing",
        kind: "info",
      });
    }
    return;
  }

  const accepted = await ask(
    `Version ${update.version} is available (you have ${update.currentVersion}).\n\nDownload and install now? The app will restart.`,
    { title: "Update available", kind: "info" },
  );
  if (!accepted) return;

  try {
    // Stop the sidecar before NSIS runs — its PyInstaller _internal/ DLLs
    // would otherwise stay locked and the install errors on overwrite. The
    // Job Object catches this too, but explicit shutdown is deterministic.
    try {
      await invoke("shutdown_sidecar");
    } catch (err) {
      console.warn("shutdown_sidecar failed, relying on Job Object:", err);
    }
    await update.downloadAndInstall();
    await relaunch();
  } catch (err) {
    await message(`Update failed: ${err}`, {
      title: "CFD Post-Processing",
      kind: "error",
    });
  }
}
