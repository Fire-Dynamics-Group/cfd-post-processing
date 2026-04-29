import { useMemo, useState } from "react";
import type { ChartManifest } from "../lib/api";

interface Props {
  manifest: ChartManifest;
}

interface FlatChart {
  scenarioIndex: number;
  scenarioName: string;
  filename: string;
  url: string;
  /** 1-based position within this chart's scenario. */
  positionInScenario: number;
  /** Total charts in this chart's scenario. */
  scenarioTotal: number;
}

function flatten(manifest: ChartManifest): FlatChart[] {
  const out: FlatChart[] = [];
  manifest.scenarios.forEach((s, scenarioIndex) => {
    s.charts.forEach((c, i) => {
      out.push({
        scenarioIndex,
        scenarioName: s.name,
        filename: c.filename,
        url: c.url,
        positionInScenario: i + 1,
        scenarioTotal: s.charts.length,
      });
    });
  });
  return out;
}

export default function ChartViewer({ manifest }: Props) {
  const flat = useMemo(() => flatten(manifest), [manifest]);
  const [index, setIndex] = useState(0);

  if (flat.length === 0) {
    return <div className="chart-viewer empty">No charts to display.</div>;
  }

  const current = flat[Math.min(index, flat.length - 1)];

  function jumpToScenario(name: string) {
    const target = flat.findIndex((c) => c.scenarioName === name);
    if (target >= 0) setIndex(target);
  }

  return (
    <div className="chart-viewer">
      <div className="chart-viewer-toolbar">
        <label>
          Scenario:{" "}
          <select
            value={current.scenarioName}
            onChange={(e) => jumpToScenario(e.target.value)}
          >
            {manifest.scenarios.map((s) => (
              <option key={s.name} value={s.name}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <span className="chart-position">
          {current.scenarioName} — {current.positionInScenario} of{" "}
          {current.scenarioTotal}
        </span>
      </div>

      <img src={current.url} alt={current.filename} />

      <div className="chart-viewer-nav">
        <button
          type="button"
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
          disabled={index === 0}
        >
          ← Prev
        </button>
        <button
          type="button"
          onClick={() => setIndex((i) => Math.min(flat.length - 1, i + 1))}
          disabled={index >= flat.length - 1}
        >
          Next →
        </button>
      </div>
    </div>
  );
}
