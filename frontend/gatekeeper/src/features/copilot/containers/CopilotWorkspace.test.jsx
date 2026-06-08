import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { CopilotWorkspace } from "./CopilotWorkspace";

vi.mock("../hooks/useCopilotSession", () => ({
  useCopilotSession: vi.fn(),
}));

import { useCopilotSession } from "../hooks/useCopilotSession";

describe("CopilotWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCopilotSession.mockReturnValue({
      messages: [
        { id: "u1", role: "user", content: "Hello" },
        { id: "a1", role: "assistant", content: "Hi there", streaming: false },
      ],
      activityEvents: [],
      currentPlan: {
        steps: [
          {
            step_id: "s1",
            tool_name: "replay_lookup",
            rationale: "Check evidence",
            expected_evidence: "graph nodes",
          },
        ],
        step_cursor: 0,
      },
      pendingApproval: null,
      status: "running",
      isStreaming: false,
      isAwaitingApproval: false,
      error: null,
      isLoading: false,
      isBootstrapping: false,
      isInputReady: true,
      ask: vi.fn(),
      resume: vi.fn(),
      clearError: vi.fn(),
    });
  });

  it("composes plan, chat, and status without business logic", () => {
    render(
      <CopilotWorkspace repositoryId="repo-1" mrIid={42} enabled />,
    );

    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("Investigation Plan")).toBeInTheDocument();
    expect(screen.getByText("replay_lookup")).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("Hi there")).toBeInTheDocument();
    expect(useCopilotSession).toHaveBeenCalledWith({
      repositoryId: "repo-1",
      mrIid: 42,
      conversationId: undefined,
      enabled: true,
    });
  });
});
