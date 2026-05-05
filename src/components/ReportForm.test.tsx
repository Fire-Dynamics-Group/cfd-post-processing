import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// All Tauri imports must be mocked before the component imports them.
// vi.mock() is hoisted to the top of the file, so any references inside
// its factory must come from vi.hoisted() — that's the only thing hoisted
// alongside the mock.
const { dialogOpen, openerOpenPath, openerReveal } = vi.hoisted(() => ({
  dialogOpen: vi.fn(),
  openerOpenPath: vi.fn(async () => undefined),
  openerReveal: vi.fn(async () => undefined),
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(async () => 8765),
}));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: dialogOpen }));
vi.mock("@tauri-apps/plugin-opener", () => ({
  openPath: openerOpenPath,
  revealItemInDir: openerReveal,
}));

import ReportForm from "./ReportForm";


async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  // user-event's `type` must be awaited sequentially — running in parallel
  // races on focus and drops keystrokes.
  await user.type(screen.getByLabelText(/Path to runs/i), "C:/runs");
  await user.type(screen.getByLabelText(/Client name/i), "Acme");
  await user.type(screen.getByLabelText(/Project name/i), "Proj");
  await user.type(screen.getByLabelText(/Project Location/i), "London");
  await user.type(screen.getByLabelText(/Senior's email prefix/i), "ian");
}


function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}


/** A discovery response. Defaults to a single scenario so existing tests
 * that only care about the post-pick flow can stay terse. Tests that need
 * to exercise the checklist itself pass an explicit list. */
function discoverResponse(
  scenarios: Array<{ id: string; label?: string }> = [
    { id: "FS1_FSA", label: "FS1_FSA" },
  ],
) {
  return jsonResponse({
    scenarios: scenarios.map((s) => ({
      id: s.id,
      label: s.label ?? s.id,
      fds_dir: `C:/runs/${s.id}`,
    })),
  });
}


/** Click the Discover button and wait for the picker view to appear.
 * Caller is responsible for mocking the discover response and filling
 * any fields it needs first. */
async function clickDiscoverAndWaitForPicker(
  user: ReturnType<typeof userEvent.setup>,
) {
  await user.click(
    screen.getByRole("button", { name: /Discover scenarios/i }),
  );
  await waitFor(() => {
    expect(
      screen.getByRole("button", { name: /^Create Report/i }),
    ).toBeInTheDocument();
  });
}


function runningState(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "abc",
    status: "running",
    step: "charting",
    progress_pct: 0.5,
    output_path: null,
    warnings: [],
    error: null,
    ...overrides,
  };
}


describe("ReportForm", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("renders the seven legacy form fields plus the OUTPUT_DIR picker", () => {
    render(<ReportForm />);
    expect(screen.getByLabelText(/Path to runs/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Client name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Project name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Project Location/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Senior's email prefix/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Max Travel Distance/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Output folder/i)).toBeInTheDocument();
    // Initial action is "Discover scenarios" — the Create Report button
    // only appears in the picker view after discovery succeeds.
    expect(
      screen.getByRole("button", { name: /Discover scenarios/i }),
    ).toBeEnabled();
  });

  it("posts the form to /jobs with selected SCENARIOS and shows running progress", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(discoverResponse([{ id: "FS1_FSA" }]))
      .mockResolvedValueOnce(jsonResponse({ job_id: "abc" }, 202))
      .mockResolvedValue(jsonResponse(runningState()));

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ReportForm />);
    await fillRequiredFields(user);
    await clickDiscoverAndWaitForPicker(user);
    await user.click(screen.getByRole("button", { name: /^Create Report/i }));

    // First poll fires after 1500ms.
    await vi.advanceTimersByTimeAsync(1500);

    await waitFor(() =>
      expect(screen.getByText(/Generating charts/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/50%/)).toBeInTheDocument();
    // Submit button is disabled while busy.
    expect(screen.getByRole("button", { name: /Working/i })).toBeDisabled();

    // Verify the /jobs POST (second fetch — first was /discover-scenarios)
    // carried the expected JSON body, including SCENARIOS from the picker.
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8765/jobs",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
    const postBody = JSON.parse(
      (fetchMock.mock.calls[1][1] as RequestInit).body as string,
    );
    expect(postBody).toMatchObject({
      PATH: "C:/runs",
      CLIENT_NAME: "Acme",
      PROJECT_NAME: "Proj",
      PROJECT_LOCATION: "London",
      EMAIL_PREFIX: "ian",
      GUIDANCE: "BS9991",
      HAS_EXTENDED_TRAVEL: true,
      SCENARIOS: ["FS1_FSA"],
    });
  });

  it("renders post-completion Open in Word + Reveal in Folder buttons that invoke the opener plugin", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(discoverResponse())
      .mockResolvedValueOnce(jsonResponse({ job_id: "abc" }, 202))
      .mockResolvedValueOnce(
        jsonResponse(
          runningState({
            status: "completed",
            step: "done",
            progress_pct: 1,
            output_path: "C:/out/Proj.docx",
          }),
        ),
      );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ReportForm />);
    await fillRequiredFields(user);
    await clickDiscoverAndWaitForPicker(user);
    await user.click(screen.getByRole("button", { name: /^Create Report/i }));

    await vi.advanceTimersByTimeAsync(1500);

    await waitFor(() =>
      expect(screen.getByText("C:/out/Proj.docx")).toBeInTheDocument(),
    );
    vi.useRealTimers();
    // Fresh user-event session bound to real timers; the previous one was
    // configured with advanceTimers and would break once timers go real.
    const realUser = userEvent.setup();

    await realUser.click(screen.getByRole("button", { name: /Open in Word/i }));
    expect(openerOpenPath).toHaveBeenCalledWith("C:/out/Proj.docx");

    await realUser.click(
      screen.getByRole("button", { name: /Reveal in Folder/i }),
    );
    expect(openerReveal).toHaveBeenCalledWith("C:/out/Proj.docx");
  });

  it("renders inline field-level errors when the server returns 422", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(discoverResponse())
      .mockResolvedValueOnce(
        jsonResponse(
          {
            detail: [
              {
                loc: ["body", "PROJECT_NAME"],
                msg: "field required",
                type: "missing",
              },
              {
                loc: ["body", "CLIENT_NAME"],
                msg: "field required",
                type: "missing",
              },
            ],
          },
          422,
        ),
      );

    const user = userEvent.setup();
    render(<ReportForm />);
    // PATH must be filled to discover, but other required fields are left
    // empty — the server-side 422 (mocked above) drives the field-error UI.
    await user.type(screen.getByLabelText(/Path to runs/i), "C:/runs");
    await clickDiscoverAndWaitForPicker(user);
    await user.click(screen.getByRole("button", { name: /^Create Report/i }));

    await waitFor(() => {
      const matches = screen.getAllByText(/field required/i);
      expect(matches.length).toBe(2);
    });
    expect(
      screen.getByText(/Please fix the highlighted fields/i),
    ).toBeInTheDocument();
  });

  it("shows a 409 'already running' banner when the server rejects a duplicate POST", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(discoverResponse())
      .mockResolvedValueOnce(
        jsonResponse({ detail: "A report job is already running" }, 409),
      );

    const user = userEvent.setup();
    render(<ReportForm />);
    await fillRequiredFields(user);
    await clickDiscoverAndWaitForPicker(user);
    await user.click(screen.getByRole("button", { name: /^Create Report/i }));

    await waitFor(() =>
      expect(screen.getByText("HTTP 409")).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/A report job is already running/i),
    ).toBeInTheDocument();
  });

  it("renders a Pipeline failed banner WITHOUT a Copy diagnostic button", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetch)
      .mockResolvedValueOnce(discoverResponse())
      .mockResolvedValueOnce(jsonResponse({ job_id: "abc" }, 202))
      .mockResolvedValueOnce(
        jsonResponse(
          runningState({
            status: "failed",
            step: "parsing",
            error: {
              type: "PipelineError",
              message: "No scenarios found in PATH",
              step: "parsing",
              details: null,
              traceback: null,
            },
          }),
        ),
      );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ReportForm />);
    await fillRequiredFields(user);
    await clickDiscoverAndWaitForPicker(user);
    await user.click(screen.getByRole("button", { name: /^Create Report/i }));
    await vi.advanceTimersByTimeAsync(1500);

    await waitFor(() =>
      expect(screen.getByText(/Pipeline failed/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/No scenarios found in PATH/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Copy diagnostic/i }),
    ).toBeNull();
  });

  it("renders an Internal error banner WITH a Copy diagnostic button and traceback", async () => {
    // Clipboard side-effect is unit-tested at the lib level (api.test.ts);
    // here we only verify the UI rendering of the InternalError variant.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetch)
      .mockResolvedValueOnce(discoverResponse())
      .mockResolvedValueOnce(jsonResponse({ job_id: "abc" }, 202))
      .mockResolvedValueOnce(
        jsonResponse(
          runningState({
            status: "failed",
            step: "rendering",
            error: {
              type: "InternalError",
              message: "RuntimeError: kaboom",
              step: "rendering",
              details: null,
              traceback: "Traceback...\n  RuntimeError: kaboom\n",
            },
          }),
        ),
      );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ReportForm />);
    await fillRequiredFields(user);
    await clickDiscoverAndWaitForPicker(user);
    await user.click(screen.getByRole("button", { name: /^Create Report/i }));
    await vi.advanceTimersByTimeAsync(1500);

    await waitFor(() =>
      expect(screen.getByText(/Internal error/i)).toBeInTheDocument(),
    );
    expect(
      screen.getAllByText(/RuntimeError: kaboom/i).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: /Copy diagnostic/i }),
    ).toBeInTheDocument();
    // Traceback collapsible exists (summary + pre both contain the word).
    expect(screen.getAllByText(/Traceback/i).length).toBeGreaterThan(0);
  });

  it("stops polling once the job reaches a terminal status", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(discoverResponse())
      .mockResolvedValueOnce(jsonResponse({ job_id: "abc" }, 202))
      .mockResolvedValueOnce(
        jsonResponse(
          runningState({
            status: "completed",
            step: "done",
            progress_pct: 1,
            output_path: "C:/out/Proj.docx",
          }),
        ),
      );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ReportForm />);
    await fillRequiredFields(user);
    await clickDiscoverAndWaitForPicker(user);
    await user.click(screen.getByRole("button", { name: /^Create Report/i }));

    // First poll: terminal. After this, the interval should be cleared.
    await vi.advanceTimersByTimeAsync(1500);
    await waitFor(() =>
      expect(screen.getByText("C:/out/Proj.docx")).toBeInTheDocument(),
    );

    const callsAfterFirstPoll = fetchMock.mock.calls.length;
    // Advance way past several poll cycles. No new GETs should fire.
    await vi.advanceTimersByTimeAsync(15000);
    expect(fetchMock.mock.calls.length).toBe(callsAfterFirstPoll);
  });

  it("shows discovered scenarios as default-checked checkboxes after Discover", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      discoverResponse([{ id: "FS1_FSA" }, { id: "FS2_MOE" }, { id: "FS3_FSA" }]),
    );

    const user = userEvent.setup();
    render(<ReportForm />);
    await fillRequiredFields(user);
    await clickDiscoverAndWaitForPicker(user);

    const checkboxes = await screen.findAllByRole("checkbox");
    expect(checkboxes).toHaveLength(3);
    checkboxes.forEach((cb) => expect(cb).toBeChecked());
  });

  it("posts only the checked scenarios when the user unchecks one", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(
        discoverResponse([
          { id: "FS1_FSA" },
          { id: "FS2_MOE" },
          { id: "FS3_FSA" },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse({ job_id: "abc" }, 202))
      .mockResolvedValue(jsonResponse(runningState()));

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ReportForm />);
    await fillRequiredFields(user);
    await clickDiscoverAndWaitForPicker(user);

    const checkboxes = await screen.findAllByRole("checkbox");
    // Uncheck the middle scenario.
    await user.click(checkboxes[1]);
    expect(checkboxes[1]).not.toBeChecked();

    await user.click(screen.getByRole("button", { name: /^Create Report/i }));

    const postBody = JSON.parse(
      (fetchMock.mock.calls[1][1] as RequestInit).body as string,
    );
    expect(postBody.SCENARIOS).toEqual(["FS1_FSA", "FS3_FSA"]);
  });

  it("disables Create Report when every scenario is unchecked", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      discoverResponse([{ id: "FS1_FSA" }, { id: "FS2_MOE" }]),
    );

    const user = userEvent.setup();
    render(<ReportForm />);
    await fillRequiredFields(user);
    await clickDiscoverAndWaitForPicker(user);

    const checkboxes = await screen.findAllByRole("checkbox");
    for (const cb of checkboxes) {
      await user.click(cb);
    }

    const createButton = screen.getByRole("button", { name: /^Create Report/i });
    expect(createButton).toBeDisabled();
    expect(createButton).toHaveTextContent("(0)");
  });

  it("shows an empty-state when discovery returns no scenarios", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(discoverResponse([]));

    const user = userEvent.setup();
    render(<ReportForm />);
    await fillRequiredFields(user);
    await user.click(
      screen.getByRole("button", { name: /Discover scenarios/i }),
    );

    await waitFor(() =>
      expect(
        screen.getByText(/No scenario folders found/i),
      ).toBeInTheDocument(),
    );
    // Create Report doesn't appear (or is disabled) when no scenarios were
    // discovered — the user has nothing to submit.
    const createButton = screen.queryByRole("button", { name: /^Create Report/i });
    if (createButton) expect(createButton).toBeDisabled();
  });
});
