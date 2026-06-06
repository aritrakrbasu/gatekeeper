import { useQuery } from "@tanstack/react-query";
import { copilotApi } from "../api/copilotApi";
import { queryKeys } from "../../../services/queryClient";

/**
 * List Copilot conversations with optional repository/execution filters.
 */
export function useCopilotConversations(filters = {}, options = {}) {
  const { enabled = true, staleTime = 60 * 1000 } = options;

  return useQuery({
    queryKey: queryKeys.copilot.conversations(filters),
    queryFn: () => copilotApi.getConversations(filters),
    enabled,
    staleTime,
  });
}
