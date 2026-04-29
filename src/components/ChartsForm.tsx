import { useRef, useState, type FormEvent } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  JobRequestError,
  pollChartsJob,
  startChartsJob,
  type ChartManifest,
  type ChartsPayload,
} from "../lib/api";
import ChartViewer from "./ChartViewer";


type Status =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "running"; jobId: string; manifest: ChartManifest; total: number }
  | { kind: "ok"; manifest: ChartManifest }
  | { kind: "error"; message: string; payload: unknown };


const POLL_INTERVAL_MS = 500;


function emptyManifest(jobId: string, projectName: string): ChartManifest {
  return { job_id: jobId, project_name: projectName, scenarios: [], errors: [] };
}


export default function ChartsForm() {
  const [values, setValues] = useState<ChartsPayload>({ PATH: "", PROJECT_NAME: "" });
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  // Sentinel for aborting the polling loop when the user clicks "New
  // run" mid-flight. Polling stops the moment the ref no longer matches
  // the loop's local job_id.
  const pollingJobIdRef = useRef<string | null>(null);

  function update<K extends keyof ChartsPayload>(key: K, value: ChartsPayload[K]) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  async function pickDirectory() {
    try {
      const selected = await open({ directory: true, multiple: false });
      if (typeof selected === "string") update("PATH", selected);
    } catch (err) {
      setStatus({ kind: "error", message: String(err), payload: null });
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (status.kind === "submitting" || status.kind === "running") return;
    setStatus({ kind: "submitting" });

    try {
      const { job_id } = await startChartsJob(values);
      pollingJobIdRef.current = job_id;
      setStatus({
        kind: "running",
        jobId: job_id,
        manifest: emptyManifest(job_id, values.PROJECT_NAME),
        total: 0,
      });

      while (pollingJobIdRef.current === job_id) {
        const state = await pollChartsJob(job_id);
        if (pollingJobIdRef.current !== job_id) return;

        if (state.status === "completed") {
          setStatus({
            kind: "ok",
            manifest: {
              job_id: state.job_id,
              project_name: state.project_name,
              scenarios: state.scenarios,
              errors: state.errors,
            },
          });
          return;
        }

        if (state.status === "failed") {
          throw new JobRequestError(
            state.error ?? "Charts job failed",
            500,
            state,
          );
        }

        setStatus({
          kind: "running",
          jobId: job_id,
          manifest: {
            job_id: state.job_id,
            project_name: state.project_name,
            scenarios: state.scenarios,
            errors: state.errors,
          },
          total: state.scenarios_total,
        });
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      }
    } catch (err) {
      if (err instanceof JobRequestError) {
        setStatus({ kind: "error", message: err.message, payload: err.payload });
      } else {
        setStatus({
          kind: "error",
          message: err instanceof Error ? err.message : String(err),
          payload: null,
        });
      }
    }
  }

  function reset() {
    // Tells the polling loop to stop on its next iteration.
    pollingJobIdRef.current = null;
    setStatus({ kind: "idle" });
  }

  if (status.kind === "ok" || status.kind === "running") {
    const manifest = status.manifest;
    const isRunning = status.kind === "running";
    return (
      <div className="charts-result">
        <div className="charts-result-header">
          <h2>{manifest.project_name} — Charts</h2>
          {isRunning ? (
            <span className="charts-progress">
              {manifest.scenarios.length}
              {status.total > 0 ? ` of ${status.total}` : ""} scenarios complete…
            </span>
          ) : (
            <button type="button" className="secondary" onClick={reset}>
              New run
            </button>
          )}
        </div>
        {manifest.errors.length > 0 && (
          <ul className="warnings">
            {manifest.errors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        )}
        {manifest.scenarios.length > 0 ? (
          <ChartViewer manifest={manifest} />
        ) : (
          <div className="chart-viewer empty">
            Waiting for the first scenario to render…
          </div>
        )}
      </div>
    );
  }

  return (
    <form className="report-form" onSubmit={onSubmit}>
      <label htmlFor="charts-path">Path to runs' root directory:</label>
      <div className="path-row">
        <input
          id="charts-path"
          type="text"
          value={values.PATH}
          onChange={(e) => update("PATH", e.target.value)}
        />
        <button type="button" className="secondary" onClick={pickDirectory}>
          Browse...
        </button>
      </div>

      <label htmlFor="charts-project">Project Name:</label>
      <input
        id="charts-project"
        type="text"
        value={values.PROJECT_NAME}
        onChange={(e) => update("PROJECT_NAME", e.target.value)}
      />

      <div className="actions">
        <button type="submit" disabled={status.kind === "submitting"}>
          {status.kind === "submitting" ? "Starting…" : "Create Charts"}
        </button>
      </div>

      {status.kind === "error" && (
        <div className="status-area error">
          <div>{status.message}</div>
          {status.payload != null && (
            <pre>{JSON.stringify(status.payload, null, 2)}</pre>
          )}
        </div>
      )}
    </form>
  );
}
