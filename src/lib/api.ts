import { invoke } from "@tauri-apps/api/core";

export type Step =
  | "queued"
  | "parsing"
  | "charting"
  | "drawing"
  | "rendering"
  | "saving"
  | "done";

export type JobStatus = "running" | "completed" | "failed";
export type ErrorType = "ValidationError" | "PipelineError" | "InternalError";

export interface ReportPayload {
  PATH: string;
  CLIENT_NAME: string;
  PROJECT_NAME: string;
  PROJECT_LOCATION: string;
  EMAIL_PREFIX: string;
  HAS_EXTENDED_TRAVEL: boolean;
  MAX_TD: number | null;
  GUIDANCE: "BS9991" | "ADB";
  OUTPUT_DIR?: string | null;
}

export interface JobError {
  type: ErrorType;
  message: string;
  step?: Step | null;
  details?: Record<string, unknown> | null;
  traceback?: string | null;
}

export interface JobState {
  id: string;
  status: JobStatus;
  step: Step;
  progress_pct: number;
  output_path: string | null;
  warnings: string[];
  error: JobError | null;
}

let cachedPort: number | null = null;

async function getSidecarPort(): Promise<number> {
  if (cachedPort != null) return cachedPort;
  cachedPort = await invoke<number>("get_sidecar_port");
  return cachedPort;
}

async function baseUrl(): Promise<string> {
  return `http://127.0.0.1:${await getSidecarPort()}`;
}

export class JobRequestError extends Error {
  constructor(
    message: string,
    public status: number,
    public payload: unknown,
  ) {
    super(message);
    this.name = "JobRequestError";
  }
}

/** Map a Pydantic 422 error payload into ``{ FIELD_NAME: error_message }``.
 * Pydantic produces ``{ detail: [{ loc: ['body', FIELD], msg, type }, ...] }``.
 * Anything that doesn't match that shape returns ``{}`` so callers can fall
 * back to the generic banner.
 */
export function parseFieldErrors(payload: unknown): Record<string, string> {
  const result: Record<string, string> = {};
  if (typeof payload !== "object" || payload === null) return result;
  const detail = (payload as { detail?: unknown }).detail;
  if (!Array.isArray(detail)) return result;
  for (const entry of detail) {
    if (typeof entry !== "object" || entry === null) continue;
    const loc = (entry as { loc?: unknown }).loc;
    const msg = (entry as { msg?: unknown }).msg;
    if (!Array.isArray(loc) || typeof msg !== "string") continue;
    // Skip the leading "body" segment; map the field name to the message.
    const field = loc.slice(1).join(".");
    if (field) result[field] = msg;
  }
  return result;
}

async function parseBody(response: Response): Promise<unknown> {
  // Reading .json() first would consume the stream and leave .text() with
  // "Body is unusable". Read text once, then try to parse.
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function createJob(payload: ReportPayload): Promise<{ job_id: string }> {
  const url = `${await baseUrl()}/jobs`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new JobRequestError(
      `HTTP ${response.status}`,
      response.status,
      await parseBody(response),
    );
  }
  return response.json();
}

export interface ChartsPayload {
  PATH: string;
  PROJECT_NAME: string;
  SCENARIOS?: ScenarioSelection[];
}

export interface ScenarioSelection {
  /** Forward-slash relative path from the discovered root, used as a
   * unique key and as the output-dir name under ``CHARTS_BASE``. */
  id: string;
  /** Display name. The "FSA" detection used to derive the firefighting
   * flag reads this string, so labels should preserve the FDS run
   * folder's name (which always contains "FSA" for FSA scenarios). */
  label: string;
  /** Absolute path to the folder holding the .fds, _devc.csv, _hrr.csv. */
  fds_dir: string;
}

export interface ChartManifestEntry {
  filename: string;
  /** Absolute URL — already prefixed with the sidecar base URL. */
  url: string;
}

export interface ChartScenario {
  name: string;
  charts: ChartManifestEntry[];
}

export interface ChartManifest {
  job_id: string;
  project_name: string;
  scenarios: ChartScenario[];
  /** Verbose per-file messages from the legacy chart helpers. Kept
   * around for diagnostics; the UI renders ``skipped`` instead. */
  errors: string[];
  /** Names of subdirectories that looked like scenarios but lacked the
   * required FDS files and were skipped. */
  skipped: string[];
}

export type ChartsJobStatus = "running" | "completed" | "failed";

/** Snapshot of a charts-mode job. ``scenarios`` grows progressively as the
 * worker thread renders each subdirectory. ``scenarios_total`` is set
 * once discovery completes (which happens early in the worker). */
export interface ChartsJobState {
  job_id: string;
  status: ChartsJobStatus;
  project_name: string;
  scenarios: ChartScenario[];
  scenarios_total: number;
  errors: string[];
  skipped: string[];
  error: string | null;
}

/** Discover scenario folders under ``PATH``. Used to populate the
 * folder-picker checklist in charts mode. */
export async function discoverChartsScenarios(
  path: string,
): Promise<{ scenarios: ScenarioSelection[] }> {
  const response = await fetch(
    `${await baseUrl()}/discover-charts-scenarios`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ PATH: path }),
    },
  );
  if (!response.ok) {
    throw new JobRequestError(
      `HTTP ${response.status}`,
      response.status,
      await parseBody(response),
    );
  }
  return response.json();
}

/** Kick off a charts job. Returns the ``job_id`` straight away — the
 * caller must poll ``pollChartsJob`` to see scenarios as they land. */
export async function startChartsJob(payload: ChartsPayload): Promise<{ job_id: string }> {
  const response = await fetch(`${await baseUrl()}/generate-charts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new JobRequestError(
      `HTTP ${response.status}`,
      response.status,
      await parseBody(response),
    );
  }
  return response.json();
}

/** Fetch the current snapshot of a charts job. Server-relative chart URLs
 * are rewritten to absolute so callers can drop them straight into
 * ``<img src=...>``. */
export async function pollChartsJob(jobId: string): Promise<ChartsJobState> {
  const base = await baseUrl();
  const response = await fetch(`${base}/generate-charts/${jobId}`);
  if (!response.ok) {
    throw new JobRequestError(
      `HTTP ${response.status}`,
      response.status,
      await parseBody(response),
    );
  }
  const state = (await response.json()) as ChartsJobState;
  return {
    ...state,
    scenarios: state.scenarios.map((s) => ({
      ...s,
      charts: s.charts.map((c) => ({ ...c, url: `${base}${c.url}` })),
    })),
  };
}

/** Convenience: start a job and poll until it reaches a terminal status,
 * returning the final manifest. Used by tests / non-progressive callers;
 * UI flows that want progressive updates should use ``startChartsJob`` +
 * ``pollChartsJob`` directly. */
export async function generateCharts(payload: ChartsPayload): Promise<ChartManifest> {
  const { job_id } = await startChartsJob(payload);
  // Tight-but-bounded polling. Tests run with a fake fetch so the loop
  // resolves on the first poll; live use sees ~500ms cadence.
  for (;;) {
    const state = await pollChartsJob(job_id);
    if (state.status === "completed") {
      return {
        job_id: state.job_id,
        project_name: state.project_name,
        scenarios: state.scenarios,
        errors: state.errors,
        skipped: state.skipped,
      };
    }
    if (state.status === "failed") {
      throw new JobRequestError(
        state.error ?? "charts job failed",
        500,
        state,
      );
    }
    await new Promise((r) => setTimeout(r, 500));
  }
}

export async function pollJob(jobId: string): Promise<JobState> {
  const url = `${await baseUrl()}/jobs/${jobId}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new JobRequestError(
      `HTTP ${response.status}`,
      response.status,
      await parseBody(response),
    );
  }
  return response.json();
}

// Lazy-import so the Tauri shell plugin isn't pulled into the bundle until
// after a report completes (and so non-Tauri test/storybook contexts don't
// fail to resolve the import).
export async function openInWord(path: string): Promise<void> {
  const { openPath } = await import("@tauri-apps/plugin-opener");
  await openPath(path);
}

export async function revealInFolder(path: string): Promise<void> {
  const { revealItemInDir } = await import("@tauri-apps/plugin-opener");
  await revealItemInDir(path);
}

/** Build the JSON blob that the Copy diagnostic button writes to the
 * clipboard. Pure so we can unit-test the contract independent of any
 * navigator.clipboard mock acrobatics. */
export function buildDiagnosticBlob(state: JobState): string {
  return JSON.stringify(
    {
      error: state.error,
      step: state.step,
      progress_pct: state.progress_pct,
      warnings: state.warnings,
    },
    null,
    2,
  );
}

/** Copy a diagnostic blob to the clipboard with a textarea fallback for
 * environments without ``navigator.clipboard``. */
export async function copyDiagnostic(state: JobState): Promise<void> {
  const blob = buildDiagnosticBlob(state);
  try {
    await navigator.clipboard.writeText(blob);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = blob;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
}
