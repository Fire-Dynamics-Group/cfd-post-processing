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


/** All current flows go: discover -> pick -> submit -> poll. The two
 * legacy tests below pin partial-progress / skipped / error rendering and
 * don't care about discovery details — they share this minimal stub of a
 * single-scenario discovery so each test only mocks what's actually
 * being verified. */
function discoverResponse(scenarios: Array<{ id: string; label?: string }> = [
  { id: "FS1_FSA", label: "FS1_FSA" },
]) {
  return new Response(
    JSON.stringify({
      scenarios: scenarios.map((s) => ({
        id: s.id,
        label: s.label ?? s.id,
        fds_dir: `C:/runs/${s.id}`,
      })),
    }),
    { status: 200 },
  );
}


async function clickThroughToPicker(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/path to runs/i), "C:/runs");
  await user.type(screen.getByLabelText(/project name/i), "Test");
  await user.click(screen.getByRole("button", { name: /discover scenarios/i }));
  await waitFor(() => {
    expect(
      screen.getByRole("button", { name: /^create charts/i }),
    ).toBeInTheDocument();
  });
  await user.click(screen.getByRole("button", { name: /^create charts/i }));
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
      // POST /discover-scenarios -> 2 scenarios
      .mockResolvedValueOnce(
        discoverResponse([
          { id: "FS1_FSA" },
          { id: "FS2_MOE" },
        ]),
      )
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
          skipped: [],
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
          skipped: [],
          error: null,
        }),
      );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ChartsForm />);

    await clickThroughToPicker(user);

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

  it("renders a tidy 'Skipped folders' block when the response includes skipped names", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    vi.mocked(fetch)
      .mockResolvedValueOnce(discoverResponse([{ id: "FS1_FSA" }, { id: "FS2_Rerun" }]))
      .mockResolvedValueOnce(postResponse("JOB"))
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
          ],
          scenarios_total: 2,
          errors: [
            "No fds file found in C:/.../FS2_Rerun for scenario:FS2_Rerun. Please add fds file.",
          ],
          skipped: ["FS2_Rerun"],
          error: null,
        }),
      );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ChartsForm />);

    await clickThroughToPicker(user);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /new run/i }),
      ).toBeInTheDocument();
    });

    // The clean per-folder summary is shown…
    expect(screen.getByText(/Skipped folders:/i)).toBeInTheDocument();
    expect(screen.getByText("FS2_Rerun", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/no FDS data — skipped/i)).toBeInTheDocument();

    // …and the verbose legacy "Please add X file" wording does NOT leak
    // into the UI.
    expect(screen.queryByText(/Please add/i)).not.toBeInTheDocument();
  });

  it("discovers scenarios, lets the user pick a subset, then runs only those", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    vi.mocked(fetch)
      // POST /discover-scenarios -> 3 scenarios
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            scenarios: [
              { id: "FS1_FDS", label: "FS1_FDS", fds_dir: "C:/runs/FS1_FDS" },
              { id: "FS2_FDS", label: "FS2_FDS", fds_dir: "C:/runs/FS2_FDS" },
              {
                id: "FS2_Rerun/FS2_FDS",
                label: "FS2_FDS",
                fds_dir: "C:/runs/FS2_Rerun/FS2_FDS",
              },
            ],
          }),
          { status: 200 },
        ),
      )
      // POST /generate-charts -> {job_id}
      .mockResolvedValueOnce(postResponse("JOB"))
      // First poll: completed
      .mockResolvedValueOnce(
        pollResponse({
          job_id: "JOB",
          status: "completed",
          project_name: "Test",
          scenarios: [
            {
              name: "FS1_FDS",
              charts: [{ filename: "hrr.png", url: "/charts/JOB/FS1_FDS/hrr.png" }],
            },
            {
              name: "FS2_Rerun/FS2_FDS",
              charts: [
                {
                  filename: "hrr.png",
                  url: "/charts/JOB/FS2_Rerun/FS2_FDS/hrr.png",
                },
              ],
            },
          ],
          scenarios_total: 2,
          errors: [],
          skipped: [],
          error: null,
        }),
      );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ChartsForm />);

    await user.type(screen.getByLabelText(/path to runs/i), "C:/runs");
    await user.type(screen.getByLabelText(/project name/i), "Test");
    await user.click(screen.getByRole("button", { name: /discover scenarios/i }));

    // Three checkboxes, all checked by default.
    const checkboxes = await screen.findAllByRole("checkbox");
    expect(checkboxes).toHaveLength(3);
    checkboxes.forEach((cb) => expect(cb).toBeChecked());

    // Uncheck the original FS2 (the second checkbox).
    await user.click(checkboxes[1]);
    expect(checkboxes[1]).not.toBeChecked();

    await user.click(screen.getByRole("button", { name: /create charts/i }));

    // Confirm the second fetch was the SCENARIOS-bearing POST and that
    // it carried only the two checked scenarios.
    const generateCall = vi.mocked(fetch).mock.calls.find(
      (c) => typeof c[0] === "string" && c[0].includes("/generate-charts"),
    );
    expect(generateCall).toBeTruthy();
    const sentBody = JSON.parse(generateCall![1]!.body as string);
    expect(sentBody.SCENARIOS).toHaveLength(2);
    expect(sentBody.SCENARIOS.map((s: { id: string }) => s.id)).toEqual([
      "FS1_FDS",
      "FS2_Rerun/FS2_FDS",
    ]);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /new run/i }),
      ).toBeInTheDocument();
    });
  });

  it("surfaces a failed status as an error banner", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    vi.mocked(fetch)
      .mockResolvedValueOnce(discoverResponse())
      .mockResolvedValueOnce(postResponse("JOB"))
      .mockResolvedValueOnce(
        pollResponse({
          job_id: "JOB",
          status: "failed",
          project_name: "Test",
          scenarios: [],
          scenarios_total: 0,
          errors: [],
          skipped: [],
          error: "RuntimeError: kaboom",
        }),
      );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ChartsForm />);

    await clickThroughToPicker(user);

    // The error message appears in the banner's <div> directly; the same
    // text also appears inside the diagnostic <pre> (JSON payload), so
    // match by exact text on the message node only.
    await waitFor(() => {
      expect(screen.getByText("RuntimeError: kaboom")).toBeInTheDocument();
    });
  });

  it("disables Create Charts when every scenario is unchecked", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      discoverResponse([{ id: "FS1_FSA" }, { id: "FS2_MOE" }]),
    );

    const user = userEvent.setup();
    render(<ChartsForm />);

    await user.type(screen.getByLabelText(/path to runs/i), "C:/runs");
    await user.type(screen.getByLabelText(/project name/i), "Test");
    await user.click(screen.getByRole("button", { name: /discover scenarios/i }));

    const checkboxes = await screen.findAllByRole("checkbox");
    expect(checkboxes).toHaveLength(2);
    for (const cb of checkboxes) {
      await user.click(cb);
    }

    const createButton = screen.getByRole("button", { name: /^create charts/i });
    expect(createButton).toBeDisabled();
    expect(createButton).toHaveTextContent("(0)");
  });
});
