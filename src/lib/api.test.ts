import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  JobRequestError,
  buildDiagnosticBlob,
  copyDiagnostic,
  createJob,
  generateCharts,
  parseFieldErrors,
  pollJob,
  type JobState,
  type ReportPayload,
} from "./api";

// Replace the Tauri ``invoke`` so tests don't need a Tauri runtime. We pin
// the sidecar port to a known value; the actual port number doesn't matter
// because we mock fetch as well.
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(async () => 8765),
}));


describe("parseFieldErrors", () => {
  it("returns an empty object when payload is not an object", () => {
    expect(parseFieldErrors(null)).toEqual({});
    expect(parseFieldErrors(undefined)).toEqual({});
    expect(parseFieldErrors("oops")).toEqual({});
    expect(parseFieldErrors(42)).toEqual({});
  });

  it("returns an empty object when detail is missing or not an array", () => {
    expect(parseFieldErrors({})).toEqual({});
    expect(parseFieldErrors({ detail: "string instead of array" })).toEqual({});
    expect(parseFieldErrors({ detail: { not: "an array" } })).toEqual({});
  });

  it("maps a single Pydantic error to its field name", () => {
    const payload = {
      detail: [
        { loc: ["body", "PROJECT_NAME"], msg: "field required", type: "missing" },
      ],
    };
    expect(parseFieldErrors(payload)).toEqual({
      PROJECT_NAME: "field required",
    });
  });

  it("handles multiple field errors", () => {
    const payload = {
      detail: [
        { loc: ["body", "PROJECT_NAME"], msg: "field required", type: "missing" },
        { loc: ["body", "PATH"], msg: "field required", type: "missing" },
      ],
    };
    expect(parseFieldErrors(payload)).toEqual({
      PROJECT_NAME: "field required",
      PATH: "field required",
    });
  });

  it("joins nested loc paths with a dot for nested-model fields", () => {
    // Pydantic emits ['body', 'parent', 'child'] for nested fields.
    const payload = {
      detail: [
        { loc: ["body", "parent", "child"], msg: "bad", type: "value_error" },
      ],
    };
    expect(parseFieldErrors(payload)).toEqual({ "parent.child": "bad" });
  });

  it("skips entries without a usable loc or msg", () => {
    const payload = {
      detail: [
        { loc: ["body"], msg: "no field name" },           // no field segment
        { loc: ["body", "FOO"] },                           // no msg
        { msg: "no loc at all" },                           // no loc
        null,                                                // junk
        { loc: ["body", "BAR"], msg: 42 },                  // msg not a string
        { loc: ["body", "BAZ"], msg: "ok" },                // valid
      ],
    };
    expect(parseFieldErrors(payload)).toEqual({ BAZ: "ok" });
  });
});


describe("JobRequestError", () => {
  it("preserves status and payload as own properties", () => {
    const err = new JobRequestError("HTTP 422", 422, { detail: "x" });
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("JobRequestError");
    expect(err.message).toBe("HTTP 422");
    expect(err.status).toBe(422);
    expect(err.payload).toEqual({ detail: "x" });
  });
});


describe("createJob", () => {
  const payload: ReportPayload = {
    PATH: "C:/runs",
    CLIENT_NAME: "Acme",
    PROJECT_NAME: "Test",
    PROJECT_LOCATION: "London",
    EMAIL_PREFIX: "ian",
    HAS_EXTENDED_TRAVEL: true,
    MAX_TD: 15,
    GUIDANCE: "BS9991",
  };

  beforeEach(() => {
    // Each test installs its own fetch mock.
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the parsed JSON body when the request succeeds", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ job_id: "abc" }), { status: 202 }),
    );

    await expect(createJob(payload)).resolves.toEqual({ job_id: "abc" });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/jobs",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  it("throws JobRequestError carrying the parsed JSON payload on 422", async () => {
    const errorBody = {
      detail: [
        { loc: ["body", "PROJECT_NAME"], msg: "field required", type: "missing" },
      ],
    };
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(errorBody), { status: 422 }),
    );

    await expect(createJob(payload)).rejects.toMatchObject({
      name: "JobRequestError",
      status: 422,
      payload: errorBody,
    });
  });

  it("throws JobRequestError with the raw text payload when the body isn't JSON", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response("plain text 503", { status: 503 }),
    );
    await expect(createJob(payload)).rejects.toMatchObject({
      status: 503,
      payload: "plain text 503",
    });
  });

  it("throws JobRequestError with status 409 when a job is already running", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "A report job is already running" }), {
        status: 409,
      }),
    );
    await expect(createJob(payload)).rejects.toMatchObject({ status: 409 });
  });
});


describe("buildDiagnosticBlob", () => {
  const baseState: JobState = {
    id: "abc",
    status: "failed",
    step: "rendering",
    progress_pct: 0.7,
    output_path: null,
    warnings: ["chart_x had too few rows"],
    error: {
      type: "InternalError",
      message: "RuntimeError: kaboom",
      step: "rendering",
      details: { hint: "look at devc" },
      traceback: "Traceback...\n  kaboom\n",
    },
  };

  it("includes error, step, progress, and warnings — and excludes id/output_path", () => {
    const blob = buildDiagnosticBlob(baseState);
    const parsed = JSON.parse(blob);
    expect(parsed).toEqual({
      error: baseState.error,
      step: "rendering",
      progress_pct: 0.7,
      warnings: ["chart_x had too few rows"],
    });
    expect(parsed.id).toBeUndefined();
    expect(parsed.output_path).toBeUndefined();
  });

  it("produces pretty-printed JSON (indent=2)", () => {
    const blob = buildDiagnosticBlob(baseState);
    expect(blob).toContain("\n  ");
  });
});


describe("copyDiagnostic", () => {
  const state: JobState = {
    id: "abc",
    status: "failed",
    step: "saving",
    progress_pct: 0.95,
    output_path: null,
    warnings: [],
    error: {
      type: "InternalError",
      message: "boom",
      step: "saving",
      details: null,
      traceback: "tb",
    },
  };

  it("calls navigator.clipboard.writeText with the diagnostic blob when available", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", {
      get: () => ({ writeText }),
      configurable: true,
    });

    await copyDiagnostic(state);

    expect(writeText).toHaveBeenCalledTimes(1);
    const [blob] = writeText.mock.calls[0] as unknown as [string];
    expect(JSON.parse(blob)).toEqual(JSON.parse(buildDiagnosticBlob(state)));
  });

  it("falls back to the textarea path when navigator.clipboard rejects", async () => {
    const writeText = vi.fn(async () => {
      throw new Error("permission denied");
    });
    Object.defineProperty(navigator, "clipboard", {
      get: () => ({ writeText }),
      configurable: true,
    });
    const execCommand = vi.fn(() => true);
    Object.defineProperty(document, "execCommand", {
      value: execCommand,
      configurable: true,
      writable: true,
    });

    await copyDiagnostic(state);

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(execCommand).toHaveBeenCalledWith("copy");
  });
});


describe("generateCharts", () => {
  const payload = { PATH: "C:/runs", PROJECT_NAME: "Test" };

  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts to /generate-charts and rewrites chart URLs to absolute", async () => {
    const serverBody = {
      job_id: "JOB",
      project_name: "Test",
      scenarios: [
        {
          name: "FS1_FSA",
          charts: [
            { filename: "hrr_chart.png", url: "/charts/JOB/FS1_FSA/hrr_chart.png" },
            { filename: "devc.png",      url: "/charts/JOB/FS1_FSA/devc.png" },
          ],
        },
      ],
      errors: [],
    };
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(new Response(JSON.stringify(serverBody), { status: 200 }));

    const result = await generateCharts(payload);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/generate-charts",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
    expect(result.job_id).toBe("JOB");
    expect(result.scenarios[0].charts.map((c) => c.url)).toEqual([
      "http://127.0.0.1:8765/charts/JOB/FS1_FSA/hrr_chart.png",
      "http://127.0.0.1:8765/charts/JOB/FS1_FSA/devc.png",
    ]);
  });

  it("throws JobRequestError on non-2xx", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "PATH not found: nope" }), { status: 400 }),
    );
    await expect(generateCharts(payload)).rejects.toMatchObject({
      status: 400,
      payload: { detail: "PATH not found: nope" },
    });
  });
});


describe("pollJob", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the parsed JobState on 200", async () => {
    const state = {
      id: "abc",
      status: "running",
      step: "charting",
      progress_pct: 0.5,
      output_path: null,
      warnings: [],
      error: null,
    };
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(state), { status: 200 }),
    );
    await expect(pollJob("abc")).resolves.toEqual(state);
  });

  it("throws JobRequestError on 404 (unknown job id)", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Unknown job id" }), { status: 404 }),
    );
    await expect(pollJob("missing")).rejects.toMatchObject({ status: 404 });
  });
});
