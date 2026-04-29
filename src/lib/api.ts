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
  errors: string[];
}

export async function generateCharts(payload: ChartsPayload): Promise<ChartManifest> {
  const base = await baseUrl();
  const response = await fetch(`${base}/generate-charts`, {
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
  const body = (await response.json()) as ChartManifest;
  // Server returns relative chart URLs (mounted at /charts); rewrite to
  // absolute so consumers can drop the URL straight into <img src=...>.
  return {
    ...body,
    scenarios: body.scenarios.map((s) => ({
      ...s,
      charts: s.charts.map((c) => ({ ...c, url: `${base}${c.url}` })),
    })),
  };
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
