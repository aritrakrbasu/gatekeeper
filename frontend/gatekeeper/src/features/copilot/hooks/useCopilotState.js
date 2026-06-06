import { useQuery } from "@tanstack/react-query";
import { copilotApi } from "../api/copilotApi";
import { queryKeys } from "../../../services/queryClient";

/**
 * Fetch LangGraph-derived conversation state snapshot.
 */
export function useCopilotState(conversationId, options = {}) {
  const { enabled = true, staleTime = 15 * 1000 } = options;

  return useQuery({
    queryKey: queryKeys.copilot.state(conversationId),
    queryFn: () => copilotApi.getState(conversationId),
    enabled: enabled && !!conversationId,
    staleTime,
  });
}
