import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ChartViewer from "./ChartViewer";
import type { ChartManifest } from "../lib/api";


function manifest(): ChartManifest {
  return {
    job_id: "JOB",
    project_name: "Test",
    errors: [],
    skipped: [],
    scenarios: [
      {
        name: "FS1_FSA",
        charts: [
          { filename: "hrr.png",  url: "http://x/JOB/FS1_FSA/hrr.png" },
          { filename: "devc.png", url: "http://x/JOB/FS1_FSA/devc.png" },
        ],
      },
      {
        name: "FS2_MOE",
        charts: [
          { filename: "moe_hrr.png", url: "http://x/JOB/FS2_MOE/moe_hrr.png" },
        ],
      },
    ],
  };
}


describe("ChartViewer", () => {
  it("renders the first chart of the first scenario by default", () => {
    render(<ChartViewer manifest={manifest()} />);
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "http://x/JOB/FS1_FSA/hrr.png",
    );
    expect(screen.getByText(/FS1_FSA — 1 of 2/i)).toBeInTheDocument();
  });

  it("Next advances within a scenario, then crosses into the next one", async () => {
    const user = userEvent.setup();
    render(<ChartViewer manifest={manifest()} />);
    const next = screen.getByRole("button", { name: /next/i });

    await user.click(next);
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "http://x/JOB/FS1_FSA/devc.png",
    );

    await user.click(next);
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "http://x/JOB/FS2_MOE/moe_hrr.png",
    );
    expect(screen.getByText(/FS2_MOE — 1 of 1/i)).toBeInTheDocument();
  });

  it("disables Prev on the first chart and Next on the last", async () => {
    const user = userEvent.setup();
    render(<ChartViewer manifest={manifest()} />);
    const prev = screen.getByRole("button", { name: /prev/i });
    const next = screen.getByRole("button", { name: /next/i });

    expect(prev).toBeDisabled();
    expect(next).toBeEnabled();

    await user.click(next);
    await user.click(next);

    expect(prev).toBeEnabled();
    expect(next).toBeDisabled();
  });

  it("Prev steps backwards across scenario boundaries", async () => {
    const user = userEvent.setup();
    render(<ChartViewer manifest={manifest()} />);
    const next = screen.getByRole("button", { name: /next/i });
    const prev = screen.getByRole("button", { name: /prev/i });

    await user.click(next);
    await user.click(next); // last chart, FS2_MOE
    await user.click(prev);
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "http://x/JOB/FS1_FSA/devc.png",
    );
    expect(screen.getByText(/FS1_FSA — 2 of 2/i)).toBeInTheDocument();
  });

  it("Scenario picker jumps to the first chart of the selected scenario", async () => {
    const user = userEvent.setup();
    render(<ChartViewer manifest={manifest()} />);

    await user.selectOptions(screen.getByRole("combobox"), "FS2_MOE");

    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "http://x/JOB/FS2_MOE/moe_hrr.png",
    );
  });

  it("renders an empty state when there are no charts", () => {
    render(
      <ChartViewer
        manifest={{
          job_id: "JOB",
          project_name: "Test",
          errors: [],
          skipped: [],
          scenarios: [],
        }}
      />,
    );
    expect(screen.getByText(/no charts/i)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
