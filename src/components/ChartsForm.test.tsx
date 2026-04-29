import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// vi.mock() is hoisted; references inside the factory must come from
// vi.hoisted() (also hoisted) or from inline expressions.
const { dialogOpen } = vi.hoisted(() => ({ dialogOpen: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(async () => 8765),
}));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: dialogOpen }));

import ChartsForm from "./ChartsForm";


function postResponse(jobId: string) {
  return new Response(JSON.stringify({ job_id: jobId }), { status: 202 });
}


function pollResponse(state: Record<string, unknown>) {
  return new Response(JSON.stringify(state), { status: 200 });
}


describe("ChartsForm progressive UI", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    dialogOpen.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("shows partial scenarios while running, then transitions to completed", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    vi.mocked(fetch)
      // POST /generate-charts -> {job_id}
      .mockResolvedValueOnce(postResponse("JOB"))
      // First poll: status=running, 1 of 2 scenarios complete.
      .mockResolvedValueOnce(
        pollResponse({
          job_id: "JOB",
          status: "running",
          project_name: "Test",
          scenarios: [
            {
              name: "FS1_FSA",
              charts: [
                { filename: "hrr.png", url: "/charts/JOB/FS1_FSA/hrr.png" },
              ],
            },
          ],
          scenarios_total: 2,
          errors: [],
          error: null,
        }),
      )
      // Second poll: completed with both scenarios.
      .mockResolvedValueOnce(
        pollResponse({
          job_id: "JOB",
          status: "completed",
          project_name: "Test",
          scenarios: [
            {
              name: "FS1_FSA",
              charts: [
                { filename: "hrr.png", url: "/charts/JOB/FS1_FSA/hrr.png" },
              ],
            },
            {
              name: "FS2_MOE",
              charts: [
                { filename: "moe_hrr.png", url: "/charts/JOB/FS2_MOE/moe_hrr.png" },
              ],
            },
          ],
          scenarios_total: 2,
          errors: [],
          error: null,
        }),
      );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ChartsForm />);

    await user.type(screen.getByLabelText(/path to runs/i), "C:/runs");
    await user.type(screen.getByLabelText(/project name/i), "Test");
    await user.click(screen.getByRole("button", { name: /create charts/i }));

    // After the first poll, the UI shows the running header + ChartViewer
    // with the single-scenario partial manifest visible.
    await waitFor(() => {
      expect(screen.getByText(/1 of 2 scenarios complete/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "http://127.0.0.1:8765/charts/JOB/FS1_FSA/hrr.png",
    );

    // Advance past the 500 ms poll interval; second poll lands and we
    // transition to the terminal "ok" state with both scenarios + a
    // "New run" button.
    await vi.advanceTimersByTimeAsync(600);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /new run/i }),
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/scenarios complete/i)).not.toBeInTheDocument();
  });

  it("surfaces a failed status as an error banner", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    vi.mocked(fetch)
      .mockResolvedValueOnce(postResponse("JOB"))
      .mockResolvedValueOnce(
        pollResponse({
          job_id: "JOB",
          status: "failed",
          project_name: "Test",
          scenarios: [],
          scenarios_total: 0,
          errors: [],
          error: "RuntimeError: kaboom",
        }),
      );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ChartsForm />);

    await user.type(screen.getByLabelText(/path to runs/i), "C:/runs");
    await user.type(screen.getByLabelText(/project name/i), "Test");
    await user.click(screen.getByRole("button", { name: /create charts/i }));

    // The error message appears in the banner's <div> directly; the same
    // text also appears inside the diagnostic <pre> (JSON payload), so
    // match by exact text on the message node only.
    await waitFor(() => {
      expect(screen.getByText("RuntimeError: kaboom")).toBeInTheDocument();
    });
  });
});
