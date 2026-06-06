import { useQuery } from "@tanstack/react-query";
import { copilotApi } from "../api/copilotApi";
import { queryKeys } from "../../../services/queryClient";

/**
 * Hydrate a Copilot conversation screen from bootstrap endpoint.
 */
export function useCopilotBootstrap(conversationId, options = {}) {
  const { enabled = true, staleTime = 30 * 1000 } = options;

  return useQuery({
    queryKey: queryKeys.copilot.bootstrap(conversationId),
    queryFn: () => copilotApi.getBootstrap(conversationId),
    enabled: enabled && !!conversationId,
    staleTime,
  });
}
