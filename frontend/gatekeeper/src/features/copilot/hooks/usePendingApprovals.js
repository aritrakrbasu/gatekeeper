import { useQuery } from "@tanstack/react-query";
import { copilotApi } from "../api/copilotApi";
import { queryKeys } from "../../../services/queryClient";

/**
 * Fetch pending Copilot approval queue.
 */
export function usePendingApprovals(filters = {}, options = {}) {
  const { enabled = true, staleTime = 30 * 1000, refetchInterval = false } =
    options;

  return useQuery({
    queryKey: queryKeys.copilot.pendingApprovals(filters.repository_id),
    queryFn: () => copilotApi.getPendingApprovals(filters),
    enabled,
    staleTime,
    refetchInterval,
  });
}
