import { useState, type FormEvent } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  generateCharts,
  JobRequestError,
  type ChartManifest,
  type ChartsPayload,
} from "../lib/api";
import ChartViewer from "./ChartViewer";


type Status =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "ok"; manifest: ChartManifest }
  | { kind: "error"; message: string; payload: unknown };


export default function ChartsForm() {
  const [values, setValues] = useState<ChartsPayload>({ PATH: "", PROJECT_NAME: "" });
  const [status, setStatus] = useState<Status>({ kind: "idle" });

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
    if (status.kind === "submitting") return;
    setStatus({ kind: "submitting" });
    try {
      const manifest = await generateCharts(values);
      setStatus({ kind: "ok", manifest });
    } catch (err) {
      if (err instanceof JobRequestError) {
        setStatus({
          kind: "error",
          message: `HTTP ${err.status}`,
          payload: err.payload,
        });
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
    setStatus({ kind: "idle" });
  }

  if (status.kind === "ok") {
    return (
      <div className="charts-result">
        <div className="charts-result-header">
          <h2>{status.manifest.project_name} — Charts</h2>
          <button type="button" className="secondary" onClick={reset}>
            New run
          </button>
        </div>
        {status.manifest.errors.length > 0 && (
          <ul className="warnings">
            {status.manifest.errors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        )}
        <ChartViewer manifest={status.manifest} />
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
          {status.kind === "submitting" ? "Generating..." : "Create Charts"}
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
