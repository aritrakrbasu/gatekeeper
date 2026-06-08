import React from "react";
import { useCopilotSession } from "../hooks/useCopilotSession";
import {
  getCopilotStatusClass,
  getCopilotStatusLabel,
} from "../utils/copilotStatus";
import {
  CopilotChatPanel,
  InvestigationPlanPanel,
  ApprovalCard,
  CopilotActivityStrip,
} from "../panels";

export function CopilotWorkspace({
  repositoryId,
  mrIid,
  conversationId,
  enabled = true,
}) {
  const session = useCopilotSession({
    repositoryId,
    mrIid,
    conversationId,
    enabled,
  });

  const {
    messages,
    activityEvents,
    currentPlan,
    pendingApproval,
    status,
    isStreaming,
    isAwaitingApproval,
    error,
    isLoading,
    isBootstrapping,
    isInputReady,
    ask,
    resume,
    clearError,
  } = session;

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {status && (
        <div className="px-4 py-2 border-b border-slate-100">
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide border ${getCopilotStatusClass(status)}`}
          >
            {getCopilotStatusLabel(status)}
          </span>
        </div>
      )}

      {error && (
        <div className="mx-4 mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 flex items-start justify-between gap-2">
          <p className="text-xs text-rose-700">{error}</p>
          <button
            type="button"
            onClick={clearError}
            className="text-xs text-rose-600 hover:text-rose-800 shrink-0"
          >
            Dismiss
          </button>
        </div>
      )}

      {isLoading ? (
        <div className="px-4 py-6 text-center text-sm text-slate-500">
          <div className="inline-block animate-spin rounded-full h-5 w-5 border-b-2 border-[#FC6D26] mb-2" />
          <p>Loading investigation session...</p>
        </div>
      ) : isBootstrapping ? (
        <div className="px-4 py-2 text-center text-xs text-slate-400">
          Restoring conversation...
        </div>
      ) : null}

      <InvestigationPlanPanel
        currentPlan={currentPlan}
        isStreaming={isStreaming}
        status={status}
      />

      <CopilotActivityStrip
        activityEvents={activityEvents}
        isStreaming={isStreaming}
      />

      <CopilotChatPanel
        messages={messages}
        isStreaming={isStreaming}
        isAwaitingApproval={isAwaitingApproval}
        isLoading={isLoading}
        isInputReady={isInputReady}
        onAsk={ask}
        approvalSlot={
          isAwaitingApproval && pendingApproval ? (
            <ApprovalCard
              pendingApproval={pendingApproval}
              onApprove={() => resume("approve")}
              onReject={() => resume("reject")}
              onModify={(modifiedArgs) => resume("modify", modifiedArgs)}
            />
          ) : null
        }
      />
    </div>
  );
}
