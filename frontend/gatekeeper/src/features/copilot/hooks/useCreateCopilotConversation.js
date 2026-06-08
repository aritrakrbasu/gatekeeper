import { useMutation, useQueryClient } from "@tanstack/react-query";
import { copilotApi } from "../api/copilotApi";
import { queryKeys } from "../../../services/queryClient";

/**
 * Create a new Copilot conversation (by execution_id or mr_iid).
 */
export function useCreateCopilotConversation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data) => copilotApi.createConversation(data),
    onSuccess: (_data, variables) => {
      if (variables?.repository_id) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.copilot.conversations({
            repository_id: variables.repository_id,
          }),
        });
      }
    },
  });
}
