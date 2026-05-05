import { useEffect, useRef, useState, type FormEvent } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  copyDiagnostic,
  createJob,
  discoverScenarios,
  JobRequestError,
  openInWord,
  parseFieldErrors,
  pollJob,
  revealInFolder,
  type JobState,
  type ReportPayload,
  type ScenarioSelection,
  type Step,
} from "../lib/api";

const INITIAL: ReportPayload = {
  PATH: "",
  CLIENT_NAME: "",
  PROJECT_NAME: "",
  PROJECT_LOCATION: "",
  EMAIL_PREFIX: "",
  HAS_EXTENDED_TRAVEL: true,
  MAX_TD: null,
  GUIDANCE: "BS9991",
  OUTPUT_DIR: null,
};

const STEP_LABEL: Record<Step, string> = {
  queued: "Queued",
  parsing: "Parsing scenarios",
  charting: "Generating charts",
  drawing: "Building figures",
  rendering: "Rendering template",
  saving: "Saving report",
  done: "Done",
};

type PickerCtx = {
  scenarios: ScenarioSelection[];
  checked: Record<string, boolean>;
};

type Status =
  | { kind: "idle" }
  | { kind: "discovering" }
  | ({ kind: "picking" } & PickerCtx)
  | ({ kind: "submitting" } & PickerCtx)
  | { kind: "running"; jobId: string; state: JobState | null }
  | { kind: "done"; state: JobState }
  | { kind: "job-error"; state: JobState }
  | { kind: "submit-error"; message: string; payload: unknown }
  | { kind: "field-errors"; fieldErrors: Record<string, string> };

export default function ReportForm() {
  const [values, setValues] = useState<ReportPayload>(INITIAL);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const pollHandle = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (pollHandle.current != null) window.clearInterval(pollHandle.current);
    },
    [],
  );

  function update<K extends keyof ReportPayload>(key: K, value: ReportPayload[K]) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  async function pickDirectoryInto(field: "PATH" | "OUTPUT_DIR") {
    try {
      const selected = await open({ directory: true, multiple: false });
      if (typeof selected === "string") update(field, selected);
    } catch (err) {
      setStatus({ kind: "submit-error", message: String(err), payload: null });
    }
  }

  function stopPolling() {
    if (pollHandle.current != null) {
      window.clearInterval(pollHandle.current);
      pollHandle.current = null;
    }
  }

  async function onDiscover(e: FormEvent) {
    e.preventDefault();
    if (
      status.kind === "discovering" ||
      status.kind === "submitting" ||
      status.kind === "running"
    )
      return;
    setStatus({ kind: "discovering" });
    try {
      const { scenarios } = await discoverScenarios(values.PATH);
      const checked: Record<string, boolean> = {};
      for (const s of scenarios) checked[s.id] = true;
      setStatus({ kind: "picking", scenarios, checked });
    } catch (err) {
      setStatus({
        kind: "submit-error",
        message: err instanceof Error ? err.message : String(err),
        payload: err instanceof JobRequestError ? err.payload : null,
      });
    }
  }

  function toggleScenario(id: string) {
    setStatus((s) =>
      s.kind === "picking"
        ? { ...s, checked: { ...s.checked, [id]: !s.checked[id] } }
        : s,
    );
  }

  function backToForm() {
    setStatus({ kind: "idle" });
  }

  async function onCreateReport() {
    if (status.kind !== "picking") return;
    const selectedIds = status.scenarios
      .filter((s) => status.checked[s.id])
      .map((s) => s.id);
    if (selectedIds.length === 0) return;
    const payload: ReportPayload = { ...values, SCENARIOS: selectedIds };
    const ctx: PickerCtx = {
      scenarios: status.scenarios,
      checked: status.checked,
    };
    setStatus({ kind: "submitting", ...ctx });
    try {
      const { job_id } = await createJob(payload);
      setStatus({ kind: "running", jobId: job_id, state: null });
      pollHandle.current = window.setInterval(async () => {
        try {
          const state = await pollJob(job_id);
          if (state.status === "running") {
            setStatus({ kind: "running", jobId: job_id, state });
          } else if (state.status === "completed") {
            stopPolling();
            setStatus({ kind: "done", state });
          } else {
            stopPolling();
            setStatus({ kind: "job-error", state });
          }
        } catch (err) {
          stopPolling();
          setStatus({
            kind: "submit-error",
            message: err instanceof Error ? err.message : String(err),
            payload: err instanceof JobRequestError ? err.payload : null,
          });
        }
      }, 1500);
    } catch (err) {
      if (err instanceof JobRequestError && err.status === 422) {
        const fieldErrors = parseFieldErrors(err.payload);
        if (Object.keys(fieldErrors).length > 0) {
          setStatus({ kind: "field-errors", fieldErrors });
          return;
        }
      }
      if (err instanceof JobRequestError) {
        setStatus({
          kind: "submit-error",
          message: `HTTP ${err.status}`,
          payload: err.payload,
        });
      } else {
        setStatus({
          kind: "submit-error",
          message: err instanceof Error ? err.message : String(err),
          payload: null,
        });
      }
    }
  }

  // Picker lifecycle owns its own view: checklist + status sections.
  // Errors that need form-field corrections (422) bounce back to the form
  // view; a fresh discover step then rebuilds the picker.
  const inPickerLifecycle =
    status.kind === "picking" ||
    status.kind === "submitting" ||
    status.kind === "running" ||
    status.kind === "done" ||
    status.kind === "job-error";

  if (inPickerLifecycle) {
    const isPicking = status.kind === "picking";
    const isSubmitting = status.kind === "submitting";
    const showPickerControls = isPicking || isSubmitting;
    const scenarios = showPickerControls ? status.scenarios : [];
    const checked = showPickerControls ? status.checked : {};
    const selectedCount = scenarios.filter((s) => checked[s.id]).length;
    const isWorking = isSubmitting || status.kind === "running";
    const runningState = status.kind === "running" ? status.state : null;

    return (
      <div className="report-picker">
        <h2>Select scenarios to report</h2>
        <p className="muted">{values.PATH}</p>
        {showPickerControls && (
          <>
            {scenarios.length === 0 ? (
              <div className="status-area">
                No scenario folders found under this path. A scenario folder
                is one that contains both <code>*_devc.csv</code> and{" "}
                <code>*_hrr.csv</code>.
              </div>
            ) : (
              <ul className="scenario-list">
                {scenarios.map((s) => (
                  <li key={s.id}>
                    <label>
                      <input
                        type="checkbox"
                        checked={!!checked[s.id]}
                        disabled={!isPicking}
                        onChange={() => toggleScenario(s.id)}
                      />
                      <span className="scenario-label">{s.label}</span>
                      {s.id !== s.label && s.id !== "" && (
                        <span className="muted scenario-path"> ({s.id})</span>
                      )}
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        {(showPickerControls || status.kind === "running") && (
          <div className="actions">
            <button
              type="button"
              className="secondary"
              onClick={backToForm}
              disabled={!isPicking}
            >
              Back
            </button>
            <button
              type="button"
              onClick={onCreateReport}
              disabled={isWorking || !isPicking || selectedCount === 0}
            >
              {isWorking ? "Working..." : `Create Report (${selectedCount})`}
            </button>
          </div>
        )}

        {runningState && (
          <div className="status-area running">
            <div>{STEP_LABEL[runningState.step]}…</div>
            <progress value={runningState.progress_pct} max={1} />
            <div className="muted">
              {Math.round(runningState.progress_pct * 100)}%
            </div>
          </div>
        )}
        {status.kind === "running" && !status.state && (
          <div className="status-area running">
            <div>Starting…</div>
          </div>
        )}

        {status.kind === "done" && status.state.output_path && (
          <div className="status-area ok">
            <div>Report saved to:</div>
            <code>{status.state.output_path}</code>
            <div className="post-actions">
              <button
                type="button"
                onClick={() => openInWord(status.state.output_path!)}
              >
                Open in Word
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => revealInFolder(status.state.output_path!)}
              >
                Reveal in Folder
              </button>
            </div>
            {status.state.warnings.length > 0 && (
              <ul className="warnings">
                {status.state.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {status.kind === "job-error" && status.state.error && (
          <div className="status-area error">
            <div>
              <strong>
                {status.state.error.type === "PipelineError"
                  ? "Pipeline failed"
                  : status.state.error.type === "ValidationError"
                    ? "Validation failed"
                    : "Internal error"}
              </strong>
              {status.state.error.step
                ? ` at ${STEP_LABEL[status.state.error.step]?.toLowerCase() ?? status.state.error.step}`
                : ""}
            </div>
            <div>{status.state.error.message}</div>
            {status.state.error.type === "InternalError" && (
              <div className="post-actions">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => copyDiagnostic(status.state)}
                >
                  Copy diagnostic
                </button>
              </div>
            )}
            {status.state.error.traceback &&
              status.state.error.type === "InternalError" && (
                <details>
                  <summary>Traceback</summary>
                  <pre>{status.state.error.traceback}</pre>
                </details>
              )}
          </div>
        )}
      </div>
    );
  }

  // Form view: idle, discovering, submit-error from /discover-scenarios or
  // a failed /jobs POST, and field-errors (422 from /jobs).
  const fieldErrors =
    status.kind === "field-errors" ? status.fieldErrors : {};

  function fieldErrorFor(name: keyof ReportPayload): string | undefined {
    return fieldErrors[name as string];
  }

  return (
    <form className="report-form" onSubmit={onDiscover}>
      <label htmlFor="path">Path to runs' root directory:</label>
      <div className="path-row">
        <input
          id="path"
          type="text"
          value={values.PATH}
          onChange={(e) => update("PATH", e.target.value)}
        />
        <button
          type="button"
          className="secondary"
          onClick={() => pickDirectoryInto("PATH")}
        >
          Browse...
        </button>
      </div>
      {fieldErrorFor("PATH") && (
        <div className="field-error">{fieldErrorFor("PATH")}</div>
      )}

      <label htmlFor="client">Client name:</label>
      <input
        id="client"
        type="text"
        value={values.CLIENT_NAME}
        onChange={(e) => update("CLIENT_NAME", e.target.value)}
      />
      {fieldErrorFor("CLIENT_NAME") && (
        <div className="field-error">{fieldErrorFor("CLIENT_NAME")}</div>
      )}

      <label htmlFor="project">Project name:</label>
      <input
        id="project"
        type="text"
        value={values.PROJECT_NAME}
        onChange={(e) => update("PROJECT_NAME", e.target.value)}
      />
      {fieldErrorFor("PROJECT_NAME") && (
        <div className="field-error">{fieldErrorFor("PROJECT_NAME")}</div>
      )}

      <label htmlFor="location">Project Location:</label>
      <input
        id="location"
        type="text"
        value={values.PROJECT_LOCATION}
        onChange={(e) => update("PROJECT_LOCATION", e.target.value)}
      />
      {fieldErrorFor("PROJECT_LOCATION") && (
        <div className="field-error">{fieldErrorFor("PROJECT_LOCATION")}</div>
      )}

      <label htmlFor="email">Senior's email prefix:</label>
      <input
        id="email"
        type="text"
        value={values.EMAIL_PREFIX}
        onChange={(e) => update("EMAIL_PREFIX", e.target.value)}
      />
      {fieldErrorFor("EMAIL_PREFIX") && (
        <div className="field-error">{fieldErrorFor("EMAIL_PREFIX")}</div>
      )}

      <label>Extended Travel Distances:</label>
      <div className="radio-row">
        <label>
          <input
            type="radio"
            name="extended"
            checked={values.HAS_EXTENDED_TRAVEL}
            onChange={() => update("HAS_EXTENDED_TRAVEL", true)}
          />
          True
        </label>
        <label>
          <input
            type="radio"
            name="extended"
            checked={!values.HAS_EXTENDED_TRAVEL}
            onChange={() => update("HAS_EXTENDED_TRAVEL", false)}
          />
          False
        </label>
      </div>

      <label htmlFor="maxtd">Max Travel Distance:</label>
      <div className="max-td-row">
        <input
          id="maxtd"
          type="number"
          step="0.1"
          value={values.MAX_TD ?? ""}
          onChange={(e) =>
            update("MAX_TD", e.target.value === "" ? null : Number(e.target.value))
          }
        />
        <span>m</span>
      </div>

      <label>Guidance Doc:</label>
      <div className="radio-row">
        <label>
          <input
            type="radio"
            name="guidance"
            checked={values.GUIDANCE === "BS9991"}
            onChange={() => update("GUIDANCE", "BS9991")}
          />
          BS9991
        </label>
        <label>
          <input
            type="radio"
            name="guidance"
            checked={values.GUIDANCE === "ADB"}
            onChange={() => update("GUIDANCE", "ADB")}
          />
          ADB
        </label>
      </div>

      <label htmlFor="output-dir">Output folder (optional, defaults to runs path):</label>
      <div className="path-row">
        <input
          id="output-dir"
          type="text"
          value={values.OUTPUT_DIR ?? ""}
          onChange={(e) =>
            update("OUTPUT_DIR", e.target.value === "" ? null : e.target.value)
          }
        />
        <button
          type="button"
          className="secondary"
          onClick={() => pickDirectoryInto("OUTPUT_DIR")}
        >
          Browse...
        </button>
      </div>

      <div className="actions">
        <button type="submit" disabled={status.kind === "discovering"}>
          {status.kind === "discovering" ? "Discovering…" : "Discover scenarios"}
        </button>
      </div>

      {status.kind === "submit-error" && (
        <div className="status-area error">
          <div>{status.message}</div>
          {status.payload != null && (
            <pre>{JSON.stringify(status.payload, null, 2)}</pre>
          )}
        </div>
      )}

      {status.kind === "field-errors" && (
        <div className="status-area error">
          <div>Please fix the highlighted fields above and try again.</div>
        </div>
      )}
    </form>
  );
}
