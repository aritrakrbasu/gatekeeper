import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../api/copilotApi", () => ({
  copilotApi: {
    getMrExecution: vi.fn(),
  },
}));

import { copilotApi } from "../api/copilotApi";
import { CopilotLauncher } from "./CopilotLauncher";

function renderLauncher(props = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <CopilotLauncher
        repositoryId="repo-1"
        mrIid={42}
        onOpen={vi.fn()}
        {...props}
      />
    </QueryClientProvider>,
  );
}

describe("CopilotLauncher", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state while preflight runs", () => {
    copilotApi.getMrExecution.mockReturnValue(new Promise(() => {}));
    renderLauncher();
    expect(screen.getByText(/Checking Copilot availability/i)).toBeInTheDocument();
  });

  it("shows unavailable message when no captured review", async () => {
    copilotApi.getMrExecution.mockRejectedValue(
      new Error("no_captured_review"),
    );
    renderLauncher();

    await waitFor(() =>
      expect(screen.getByText("Investigation unavailable")).toBeInTheDocument(),
    );
  });

  it("opens drawer when copilot is ready", async () => {
    const onOpen = vi.fn();
    copilotApi.getMrExecution.mockResolvedValue({ copilot_ready: true });

    renderLauncher({ onOpen });

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Investigate with Copilot/i }),
      ).toBeInTheDocument(),
    );

    fireEvent.click(
      screen.getByRole("button", { name: /Investigate with Copilot/i }),
    );
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});
