import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import {
  ActivityLog,
  getLogStatusClass,
  formatLogTimestamp,
} from "./ActivityLog";

describe("ActivityLog helpers", () => {
  it("maps status to color classes", () => {
    expect(getLogStatusClass("running")).toBe("text-blue-400");
    expect(getLogStatusClass("completed")).toBe("text-emerald-400");
    expect(getLogStatusClass("failed")).toBe("text-rose-400");
    expect(getLogStatusClass("info")).toBe("text-slate-300");
  });

  it("formats timestamps with en-US locale time", () => {
    const formatted = formatLogTimestamp("2026-06-06T14:30:45.000Z");
    expect(formatted).toMatch(/\d{1,2}:\d{2}:\d{2}/);
  });
});

describe("ActivityLog", () => {
  const logs = [
    {
      timestamp: "2026-06-06T14:30:45.000Z",
      status: "running",
      message: "Analyzing diff",
    },
    {
      timestamp: "2026-06-06T14:30:50.000Z",
      status: "completed",
      message: "Review complete",
    },
  ];

  it("returns null when empty and not loading", () => {
    const { container } = render(<ActivityLog logs={[]} isLoading={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders log entries with status colors", () => {
    render(<ActivityLog logs={logs} />);
    expect(screen.getByText("Analyzing diff")).toHaveClass("text-blue-400");
    expect(screen.getByText("Review complete")).toHaveClass("text-emerald-400");
    expect(screen.getByText("Analysis Progress")).toBeInTheDocument();
  });

  it("shows live indicator when isLive is true", () => {
    render(<ActivityLog logs={logs} isLive />);
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("shows loading state", () => {
    render(<ActivityLog logs={[]} isLoading title="Copilot Activity" />);
    expect(screen.getByText("Loading logs...")).toBeInTheDocument();
    expect(screen.getByText("Copilot Activity")).toBeInTheDocument();
  });
});
