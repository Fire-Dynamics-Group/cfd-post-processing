import { useEffect, useState } from "react";
import ChartsForm from "./components/ChartsForm";
import ReportForm from "./components/ReportForm";
import { checkForUpdates } from "./lib/updater";

type Mode = "report" | "charts";

export default function App() {
  const [mode, setMode] = useState<Mode>("report");

  useEffect(() => {
    checkForUpdates({ silent: true });
  }, []);

  return (
    <main className="app-shell">
      <h1>CFD Post-Processing</h1>
      <div className="mode-switch" role="tablist" aria-label="Mode">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "report"}
          className={mode === "report" ? "active" : ""}
          onClick={() => setMode("report")}
        >
          Full Report
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "charts"}
          className={mode === "charts" ? "active" : ""}
          onClick={() => setMode("charts")}
        >
          Charts Only
        </button>
      </div>
      {mode === "report" ? <ReportForm /> : <ChartsForm />}
    </main>
  );
}
