import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { STREAM_EVENTS } from "../constants/streamEvents";

const sseMocks = {
  connectAsk: vi.fn(),
  connectResume: vi.fn(),
  reconnect: vi.fn(),
  disconnect: vi.fn(),
  connectionStatus: "idle",
  lastEventId: null,
};

vi.mock("./useCopilotSSE", () => ({
  useCopilotSSE: vi.fn(({ onEvent }) => {
    sseMocks.onEvent = onEvent;
    return sseMocks;
  }),
}));

vi.mock("./useCopilotBootstrap", () => ({
  useCopilotBootstrap: vi.fn(),
}));

vi.mock("./useCopilotConversations", () => ({
  useCopilotConversations: vi.fn(),
}));

vi.mock("./useCreateCopilotConversation", () => ({
  useCreateCopilotConversation: vi.fn(),
}));

import { useCopilotBootstrap } from "./useCopilotBootstrap";
import { useCopilotConversations } from "./useCopilotConversations";
import { useCreateCopilotConversation } from "./useCreateCopilotConversation";
import { useCopilotSession } from "./useCopilotSession";
import { copilotApi } from "../api/copilotApi";

function createWrapper(queryClient) {
  return ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("useCopilotSession", () => {
  let queryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    useCopilotConversations.mockReturnValue({
      data: { items: [] },
      isLoading: false,
    });

    useCopilotBootstrap.mockReturnValue({
      data: null,
      isLoading: false,
    });

    useCreateCopilotConversation.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({
        conversation_id: "conv-created",
      }),
    });
  });

  it("uses provided conversationId without creating a new conversation", async () => {
    useCopilotBootstrap.mockReturnValue({
      data: {
        conversation: {
          last_question: "Why?",
          response_text: "Because.",
        },
        state: { status: "completed" },
        knowledge_manifest: {},
        current_plan: null,
        pending_approval: null,
      },
      isLoading: false,
    });

    const { result } = renderHook(
      () =>
        useCopilotSession({
          repositoryId: "repo-1",
          conversationId: "conv-existing",
        }),
      { wrapper: createWrapper(queryClient) },
    );

    await waitFor(() =>
      expect(result.current.conversationId).toBe("conv-existing"),
    );
    await waitFor(() => expect(result.current.messages).toHaveLength(2));
    expect(useCreateCopilotConversation().mutateAsync).not.toHaveBeenCalled();
    expect(result.current.status).toBe("completed");
  });

  it("creates a conversation when mrIid is provided", async () => {
    const mutateAsync = vi
      .fn()
      .mockResolvedValue({ conversation_id: "conv-created" });
    useCreateCopilotConversation.mockReturnValue({ mutateAsync });

    const { result } = renderHook(
      () =>
        useCopilotSession({
          repositoryId: "repo-1",
          mrIid: 42,
          enabled: true,
        }),
      { wrapper: createWrapper(queryClient) },
    );

    await waitFor(() =>
      expect(result.current.conversationId).toBe("conv-created"),
    );
    expect(mutateAsync).toHaveBeenCalledWith({
      repository_id: "repo-1",
      mr_iid: 42,
    });
  });

  it("routes response_chunk events into messages", async () => {
    useCopilotBootstrap.mockReturnValue({
      data: {
        conversation: {},
        state: { status: "running" },
        knowledge_manifest: {},
      },
      isLoading: false,
    });

    const { result } = renderHook(
      () =>
        useCopilotSession({
          repositoryId: "repo-1",
          conversationId: "conv-1",
        }),
      { wrapper: createWrapper(queryClient) },
    );

    act(() => {
      result.current.ask("Explain this MR");
    });

    expect(sseMocks.connectAsk).toHaveBeenCalledWith({
      question: "Explain this MR",
    });
    expect(result.current.messages.at(-1).streaming).toBe(true);

    await act(async () => {
      await sseMocks.onEvent({
        event: STREAM_EVENTS.RESPONSE_CHUNK,
        data: { text: "Analysis" },
      });
    });

    expect(result.current.messages.at(-1).content).toBe("Analysis");
  });

  it("updates pendingApproval on approval_required", async () => {
    const { result } = renderHook(
      () =>
        useCopilotSession({
          repositoryId: "repo-1",
          conversationId: "conv-1",
        }),
      { wrapper: createWrapper(queryClient) },
    );

    const approval = {
      reason: "Post comment",
      tool_name: "post_gitlab_mr_comment",
    };

    await act(async () => {
      await sseMocks.onEvent({
        event: STREAM_EVENTS.APPROVAL_REQUIRED,
        data: approval,
      });
    });

    expect(result.current.pendingApproval).toEqual(approval);
    expect(result.current.isAwaitingApproval).toBe(true);
    expect(result.current.isStreaming).toBe(false);
  });

  it("refetches bootstrap on done", async () => {
    const fetchSpy = vi.spyOn(copilotApi, "getBootstrap").mockResolvedValue({
      conversation: { response_text: "Final answer" },
      state: { status: "completed" },
      knowledge_manifest: {},
      current_plan: null,
      pending_approval: null,
    });

    const { result } = renderHook(
      () =>
        useCopilotSession({
          repositoryId: "repo-1",
          conversationId: "conv-1",
        }),
      { wrapper: createWrapper(queryClient) },
    );

    act(() => {
      result.current.ask("Question");
    });

    await act(async () => {
      await sseMocks.onEvent({
        event: STREAM_EVENTS.DONE,
        data: { interrupted: false },
      });
    });

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith("conv-1"));
    expect(result.current.isStreaming).toBe(false);
  });
});
