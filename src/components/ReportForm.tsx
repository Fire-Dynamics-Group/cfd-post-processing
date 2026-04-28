import { useState, type FormEvent } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { generateReport, type ReportPayload } from "../lib/api";

const INITIAL: ReportPayload = {
  PATH: "",
  CLIENT_NAME: "",
  PROJECT_NAME: "",
  PROJECT_LOCATION: "",
  EMAIL_PREFIX: "",
  HAS_EXTENDED_TRAVEL: true,
  MAX_TD: null,
  GUIDANCE: "BS9991",
};

type Status =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "ok"; body: unknown }
  | { kind: "error"; message: string };

export default function ReportForm() {
  const [values, setValues] = useState<ReportPayload>(INITIAL);
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  function update<K extends keyof ReportPayload>(key: K, value: ReportPayload[K]) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  async function pickDirectory() {
    try {
      const selected = await open({ directory: true, multiple: false });
      if (typeof selected === "string") update("PATH", selected);
    } catch (err) {
      setStatus({ kind: "error", message: String(err) });
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setStatus({ kind: "submitting" });
    try {
      const body = await generateReport(values);
      setStatus({ kind: "ok", body });
    } catch (err) {
      setStatus({ kind: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }

  return (
    <form className="report-form" onSubmit={onSubmit}>
      <label htmlFor="path">Path to runs' root directory:</label>
      <div className="path-row">
        <input
          id="path"
          type="text"
          value={values.PATH}
          onChange={(e) => update("PATH", e.target.value)}
        />
        <button type="button" className="secondary" onClick={pickDirectory}>
          Browse...
        </button>
      </div>

      <label htmlFor="client">Client name:</label>
      <input
        id="client"
        type="text"
        value={values.CLIENT_NAME}
        onChange={(e) => update("CLIENT_NAME", e.target.value)}
      />

      <label htmlFor="project">Project name:</label>
      <input
        id="project"
        type="text"
        value={values.PROJECT_NAME}
        onChange={(e) => update("PROJECT_NAME", e.target.value)}
      />

      <label htmlFor="location">Project Location:</label>
      <input
        id="location"
        type="text"
        value={values.PROJECT_LOCATION}
        onChange={(e) => update("PROJECT_LOCATION", e.target.value)}
      />

      <label htmlFor="email">Senior's email prefix:</label>
      <input
        id="email"
        type="text"
        value={values.EMAIL_PREFIX}
        onChange={(e) => update("EMAIL_PREFIX", e.target.value)}
      />

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

      <div className="actions">
        <button type="submit" disabled={status.kind === "submitting"}>
          {status.kind === "submitting" ? "Working..." : "Create Report"}
        </button>
      </div>

      {status.kind === "ok" && (
        <div className="status-area ok">
          {JSON.stringify(status.body, null, 2)}
        </div>
      )}
      {status.kind === "error" && (
        <div className="status-area error">{status.message}</div>
      )}
    </form>
  );
}
