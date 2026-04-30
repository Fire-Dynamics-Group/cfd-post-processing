import { describe, it, expect, vi, beforeEach } from "vitest";

const { check, relaunch, ask, message, invoke } = vi.hoisted(() => ({
  check: vi.fn(),
  relaunch: vi.fn(),
  ask: vi.fn(),
  message: vi.fn(),
  invoke: vi.fn(),
}));

vi.mock("@tauri-apps/plugin-updater", () => ({ check }));
vi.mock("@tauri-apps/plugin-process", () => ({ relaunch }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ ask, message }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

import { checkForUpdates } from "./updater";

function makeUpdate(opts: {
  version?: string;
  currentVersion?: string;
  downloadAndInstall?: () => Promise<void>;
}) {
  return {
    version: opts.version ?? "0.4.0",
    currentVersion: opts.currentVersion ?? "0.3.0",
    downloadAndInstall: opts.downloadAndInstall ?? vi.fn().mockResolvedValue(undefined),
  };
}

describe("checkForUpdates", () => {
  beforeEach(() => {
    check.mockReset();
    relaunch.mockReset();
    ask.mockReset();
    message.mockReset();
    invoke.mockReset();
  });

  it("returns silently when no update is available and silent=true", async () => {
    check.mockResolvedValue(null);

    await checkForUpdates({ silent: true });

    expect(message).not.toHaveBeenCalled();
    expect(ask).not.toHaveBeenCalled();
  });

  it("shows 'you're on the latest' when no update and silent=false", async () => {
    check.mockResolvedValue(null);

    await checkForUpdates({ silent: false });

    expect(message).toHaveBeenCalledTimes(1);
    expect(message).toHaveBeenCalledWith(
      "You're on the latest version.",
      expect.objectContaining({ kind: "info" }),
    );
  });

  it("swallows check() failures when silent=true", async () => {
    check.mockRejectedValue(new Error("network down"));

    await checkForUpdates({ silent: true });

    expect(message).not.toHaveBeenCalled();
  });

  it("surfaces check() failure when silent=false", async () => {
    check.mockRejectedValue(new Error("network down"));

    await checkForUpdates({ silent: false });

    expect(message).toHaveBeenCalledTimes(1);
    expect(message.mock.calls[0][1]).toMatchObject({ kind: "error" });
  });

  it("on accept: shuts down sidecar BEFORE downloading, then relaunches", async () => {
    const calls: string[] = [];
    invoke.mockImplementation(async (cmd: string) => {
      calls.push(`invoke:${cmd}`);
    });
    const downloadAndInstall = vi.fn(async () => {
      calls.push("downloadAndInstall");
    });
    relaunch.mockImplementation(async () => {
      calls.push("relaunch");
    });
    check.mockResolvedValue(makeUpdate({ downloadAndInstall }));
    ask.mockResolvedValue(true);

    await checkForUpdates({ silent: true });

    expect(calls).toEqual([
      "invoke:shutdown_sidecar",
      "downloadAndInstall",
      "relaunch",
    ]);
  });

  it("on decline: skips install and relaunch entirely", async () => {
    const downloadAndInstall = vi.fn();
    check.mockResolvedValue(makeUpdate({ downloadAndInstall }));
    ask.mockResolvedValue(false);

    await checkForUpdates({ silent: true });

    expect(invoke).not.toHaveBeenCalled();
    expect(downloadAndInstall).not.toHaveBeenCalled();
    expect(relaunch).not.toHaveBeenCalled();
  });

  it("treats shutdown_sidecar failure as non-fatal — install still runs", async () => {
    const downloadAndInstall = vi.fn().mockResolvedValue(undefined);
    invoke.mockRejectedValue(new Error("ipc broken"));
    check.mockResolvedValue(makeUpdate({ downloadAndInstall }));
    ask.mockResolvedValue(true);

    await checkForUpdates({ silent: true });

    expect(downloadAndInstall).toHaveBeenCalledTimes(1);
    expect(relaunch).toHaveBeenCalledTimes(1);
  });

  it("shows error dialog when downloadAndInstall throws", async () => {
    const downloadAndInstall = vi.fn().mockRejectedValue(new Error("install failed"));
    check.mockResolvedValue(makeUpdate({ downloadAndInstall }));
    ask.mockResolvedValue(true);

    await checkForUpdates({ silent: true });

    expect(message).toHaveBeenCalledTimes(1);
    expect(message.mock.calls[0][1]).toMatchObject({ kind: "error" });
    expect(relaunch).not.toHaveBeenCalled();
  });
});
