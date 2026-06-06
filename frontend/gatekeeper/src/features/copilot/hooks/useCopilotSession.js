import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { copilotApi } from "../api/copilotApi";
import { queryKeys } from "../../../services/queryClient";
import {
  applyStreamEvent,
  hydrateMessagesFromBootstrap,
  pickResumableConversation,
} from "../utils/applyStreamEvent";
import { useCopilotBootstrap } from "./useCopilotBootstrap";
import { useCopilotConversations } from "./useCopilotConversations";
import { useCreateCopilotConversation } from "./useCreateCopilotConversation";
import { useCopilotSSE } from "./useCopilotSSE";

/**
 * Orchestrates Copilot conversation resolution, bootstrap hydration,
 * local transcript state, and SSE event routing.
 */
export function useCopilotSession({
  repositoryId,
  mrIid,
  conversationId: conversationIdInput,
  enabled = true,
}) {
  const queryClient = useQueryClient();
  const createMutation = useCreateCopilotConversation();

  const [resolvedConversationId, setResolvedConversationId] = useState(
    conversationIdInput ?? null,
  );
  const [messages, setMessages] = useState([]);
  const [activityEvents, setActivityEvents] = useState([]);
  const [currentPlan, setCurrentPlan] = useState(null);
  const [pendingApproval, setPendingApproval] = useState(null);
  const [knowledgeManifest, setKnowledgeManifest] = useState({});
  const [status, setStatus] = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isAwaitingApproval, setIsAwaitingApproval] = useState(false);
  const [error, setError] = useState(null);
  const [resolutionStatus, setResolutionStatus] = useState(
    conversationIdInput ? "ready" : "idle",
  );

  const streamingMessageIdRef = useRef(null);
  const messagesHydratedRef = useRef(false);
  const isStreamingRef = useRef(false);
  const previousConversationIdRef = useRef(resolvedConversationId);
  const sessionStateRef = useRef({
    messages: [],
    activityEvents: [],
    knowledgeManifest: {},
    streamingMessageId: null,
  });

  useEffect(() => {
    isStreamingRef.current = isStreaming;
  }, [isStreaming]);

  useEffect(() => {
    sessionStateRef.current = {
      messages,
      activityEvents,
      knowledgeManifest,
      streamingMessageId: streamingMessageIdRef.current,
    };
  }, [messages, activityEvents, knowledgeManifest]);

  const conversationsQuery = useCopilotConversations(
    { repository_id: repositoryId },
    {
      enabled:
        enabled &&
        !!repositoryId &&
        !conversationIdInput &&
        !resolvedConversationId,
    },
  );

  const bootstrapQuery = useCopilotBootstrap(resolvedConversationId, {
    enabled: enabled && !!resolvedConversationId,
    staleTime: 0,
  });

  const refetchBootstrap = useCallback(async () => {
    if (!resolvedConversationId) {
      return null;
    }

    await queryClient.invalidateQueries({
      queryKey: queryKeys.copilot.bootstrap(resolvedConversationId),
    });

    return queryClient.fetchQuery({
      queryKey: queryKeys.copilot.bootstrap(resolvedConversationId),
      queryFn: () => copilotApi.getBootstrap(resolvedConversationId),
    });
  }, [queryClient, resolvedConversationId]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    if (conversationIdInput) {
      setResolvedConversationId(conversationIdInput);
      setResolutionStatus("ready");
      return;
    }

    if (!repositoryId || resolvedConversationId) {
      return;
    }

    if (!mrIid) {
      setResolutionStatus("idle");
      return;
    }

    let cancelled = false;

    async function resolveConversation() {
      setResolutionStatus("resolving");
      setError(null);

      try {
        const listData =
          conversationsQuery.data ??
          (await queryClient.fetchQuery({
            queryKey: queryKeys.copilot.conversations({
              repository_id: repositoryId,
            }),
            queryFn: () =>
              copilotApi.getConversations({ repository_id: repositoryId }),
          }));

        const existing = pickResumableConversation(listData?.items);
        if (existing) {
          if (!cancelled) {
            setResolvedConversationId(existing.conversation_id);
            setResolutionStatus("ready");
          }
          return;
        }

        const created = await createMutation.mutateAsync({
          repository_id: repositoryId,
          mr_iid: mrIid,
        });

        if (!cancelled) {
          setResolvedConversationId(created.conversation_id);
          setResolutionStatus("ready");
        }
      } catch (resolveError) {
        if (!cancelled) {
          setError(resolveError.message || "Failed to resolve conversation");
          setResolutionStatus("error");
        }
      }
    }

    resolveConversation();

    return () => {
      cancelled = true;
    };
  }, [
    enabled,
    repositoryId,
    mrIid,
    conversationIdInput,
    resolvedConversationId,
    conversationsQuery.data,
    queryClient,
    createMutation,
  ]);

  useEffect(() => {
    const bootstrap = bootstrapQuery.data;
    if (!bootstrap) {
      return;
    }

    setStatus(bootstrap.state?.status ?? null);
    setCurrentPlan(bootstrap.current_plan ?? bootstrap.state?.current_plan ?? null);
    setPendingApproval(
      bootstrap.pending_approval ?? bootstrap.state?.pending_approval ?? null,
    );
    setKnowledgeManifest(bootstrap.knowledge_manifest ?? {});
    setIsAwaitingApproval(
      bootstrap.state?.status === "waiting_approval" ||
        Boolean(bootstrap.pending_approval ?? bootstrap.state?.pending_approval),
    );

    if (!isStreamingRef.current && !messagesHydratedRef.current) {
      const hydrated = hydrateMessagesFromBootstrap(bootstrap);
      if (hydrated.length > 0) {
        setMessages(hydrated);
        messagesHydratedRef.current = true;
      }
    }
  }, [bootstrapQuery.data]);

  useEffect(() => {
    if (previousConversationIdRef.current === resolvedConversationId) {
      return;
    }

    previousConversationIdRef.current = resolvedConversationId;
    messagesHydratedRef.current = false;
    setMessages([]);
    setActivityEvents([]);
    setCurrentPlan(null);
    setPendingApproval(null);
    setKnowledgeManifest({});
    setStatus(null);
    setIsStreaming(false);
    setIsAwaitingApproval(false);
    setError(null);
    streamingMessageIdRef.current = null;
  }, [resolvedConversationId]);

  const handleStreamEvent = useCallback(
    async (event) => {
      const updates = applyStreamEvent(sessionStateRef.current, event);

      if (updates.messages) {
        setMessages(updates.messages);
        sessionStateRef.current.messages = updates.messages;
      }
      if (updates.activityEvents) {
        setActivityEvents(updates.activityEvents);
        sessionStateRef.current.activityEvents = updates.activityEvents;
      }
      if (updates.pendingApproval !== undefined) {
        setPendingApproval(updates.pendingApproval);
      }
      if (updates.isAwaitingApproval !== undefined) {
        setIsAwaitingApproval(updates.isAwaitingApproval);
      }
      if (updates.isStreaming !== undefined) {
        setIsStreaming(updates.isStreaming);
      }
      if (updates.error !== undefined) {
        setError(updates.error);
      }
      if (updates.knowledgeManifest) {
        setKnowledgeManifest(updates.knowledgeManifest);
        sessionStateRef.current.knowledgeManifest = updates.knowledgeManifest;
      }
      if (updates.shouldRefetchBootstrap) {
        const refreshed = await refetchBootstrap();
        if (refreshed) {
          setStatus(refreshed.state?.status ?? null);
          setCurrentPlan(
            refreshed.current_plan ?? refreshed.state?.current_plan ?? null,
          );
          setPendingApproval(
            refreshed.pending_approval ??
              refreshed.state?.pending_approval ??
              null,
          );
          setKnowledgeManifest(refreshed.knowledge_manifest ?? {});
          setIsAwaitingApproval(
            refreshed.state?.status === "waiting_approval" ||
              Boolean(
                refreshed.pending_approval ?? refreshed.state?.pending_approval,
              ),
          );
        }
      }
    },
    [refetchBootstrap],
  );

  const sse = useCopilotSSE({
    conversationId: resolvedConversationId,
    enabled: enabled && !!resolvedConversationId,
    onEvent: handleStreamEvent,
    onError: (streamError) => {
      setError(streamError.message || "Copilot stream failed");
      setIsStreaming(false);
    },
  });

  const ask = useCallback(
    (question) => {
      const trimmed = question?.trim();
      if (!resolvedConversationId || !trimmed || isStreaming) {
        return;
      }

      setError(null);

      const userMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: trimmed,
      };
      const assistantMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: "",
        streaming: true,
      };

      streamingMessageIdRef.current = assistantMessage.id;
      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setIsStreaming(true);
      sse.connectAsk({ question: trimmed });
    },
    [resolvedConversationId, isStreaming, sse],
  );

  const resume = useCallback(
    (decision, modifiedArgs) => {
      if (!resolvedConversationId || isStreaming) {
        return;
      }

      setError(null);
      setIsAwaitingApproval(false);
      setIsStreaming(true);
      sse.connectResume({
        decision,
        modified_tool_args: modifiedArgs,
        admin_confirmed: false,
      });
    },
    [resolvedConversationId, isStreaming, sse],
  );

  const clearError = useCallback(() => setError(null), []);

  return {
    conversationId: resolvedConversationId,
    messages,
    activityEvents,
    currentPlan,
    pendingApproval,
    knowledgeManifest,
    status,
    isStreaming,
    isAwaitingApproval,
    error,
    resolutionStatus,
    isLoading:
      resolutionStatus === "resolving" ||
      (Boolean(resolvedConversationId) && bootstrapQuery.isLoading),
    connectionStatus: sse.connectionStatus,
    lastEventId: sse.lastEventId,
    ask,
    resume,
    clearError,
    refetchBootstrap,
    reconnect: sse.reconnect,
    disconnect: sse.disconnect,
  };
}
