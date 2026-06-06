import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../api/copilotApi", () => ({
  copilotApi: {
    getBootstrap: vi.fn(),
    getState: vi.fn(),
    getConversations: vi.fn(),
    createConversation: vi.fn(),
    getPendingApprovals: vi.fn(),
  },
}));

import { copilotApi } from "../api/copilotApi";
import { useCopilotBootstrap } from "./useCopilotBootstrap";
import { useCopilotState } from "./useCopilotState";
import { useCopilotConversations } from "./useCopilotConversations";
import { useCreateCopilotConversation } from "./useCreateCopilotConversation";
import { usePendingApprovals } from "./usePendingApprovals";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("Copilot hooks", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("useCopilotBootstrap fetches when conversationId is set", async () => {
    copilotApi.getBootstrap.mockResolvedValue({ conversation: { id: "conv-1" } });

    const { result } = renderHook(() => useCopilotBootstrap("conv-1"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(copilotApi.getBootstrap).toHaveBeenCalledWith("conv-1");
  });

  it("useCopilotBootstrap stays disabled without conversationId", () => {
    const { result } = renderHook(() => useCopilotBootstrap(null), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(copilotApi.getBootstrap).not.toHaveBeenCalled();
  });

  it("useCopilotState fetches state snapshot", async () => {
    copilotApi.getState.mockResolvedValue({ status: "running" });

    const { result } = renderHook(() => useCopilotState("conv-1"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data.status).toBe("running");
  });

  it("useCopilotConversations passes filters to API", async () => {
    copilotApi.getConversations.mockResolvedValue({ items: [], total: 0 });

    const filters = { repository_id: "123", status: "running" };
    const { result } = renderHook(() => useCopilotConversations(filters), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(copilotApi.getConversations).toHaveBeenCalledWith(filters);
  });

  it("useCreateCopilotConversation mutates via API", async () => {
    copilotApi.createConversation.mockResolvedValue({
      conversation_id: "conv-new",
    });

    const { result } = renderHook(() => useCreateCopilotConversation(), {
      wrapper: createWrapper(),
    });

    await result.current.mutateAsync({
      repository_id: "123",
      mr_iid: 7,
    });

    expect(copilotApi.createConversation).toHaveBeenCalledWith({
      repository_id: "123",
      mr_iid: 7,
    });
  });

  it("usePendingApprovals fetches approval queue", async () => {
    copilotApi.getPendingApprovals.mockResolvedValue({ items: [], total: 0 });

    const { result } = renderHook(
      () => usePendingApprovals({ repository_id: "123" }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(copilotApi.getPendingApprovals).toHaveBeenCalledWith({
      repository_id: "123",
    });
  });
});
