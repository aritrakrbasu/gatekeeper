import React from "react";
import { useQuery } from "@tanstack/react-query";
import { copilotApi } from "../api/copilotApi";

function isNoCapturedReviewError(error) {
  const message = error?.message ?? "";
  return (
    message.includes("no_captured_review") ||
    message.includes("404") ||
    message.toLowerCase().includes("not found")
  );
}

export function CopilotLauncher({ repositoryId, mrIid, onOpen, disabled = false }) {
  const preflight = useQuery({
    queryKey: ["copilot", "mr-preflight", repositoryId, mrIid],
    queryFn: () => copilotApi.getMrExecution(repositoryId, mrIid),
    enabled: !disabled && !!repositoryId && !!mrIid,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  if (disabled || !repositoryId || !mrIid) {
    return null;
  }

  if (preflight.isLoading) {
    return (
      <div className="flex items-center gap-2 px-4 py-3 rounded-2xl border border-slate-100 bg-slate-50/80">
        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-[#FC6D26]" />
        <span className="text-xs text-slate-500">Checking Copilot availability...</span>
      </div>
    );
  }

  if (preflight.isError || !preflight.data?.copilot_ready) {
    const unavailable = preflight.isError && isNoCapturedReviewError(preflight.error);

    return (
      <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
        <p className="text-xs font-semibold text-slate-700">
          {unavailable
            ? "Investigation unavailable"
            : "Copilot unavailable"}
        </p>
        <p className="text-[11px] text-slate-500 mt-1">
          {unavailable
            ? "No captured ARIL review execution exists for this merge request yet. Complete a Gatekeeper review first."
            : preflight.error?.message ??
              "Copilot cannot investigate this merge request right now."}
        </p>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full flex items-center justify-between gap-3 rounded-2xl border border-[#FC6D26]/20 bg-[#FC6D26]/5 hover:bg-[#FC6D26]/10 px-4 py-3 transition-colors text-left group"
    >
      <div className="min-w-0">
        <p className="text-sm font-bold text-slate-900 group-hover:text-[#FC6D26] transition-colors">
          Investigate with Copilot
        </p>
        <p className="text-[11px] text-slate-500 mt-0.5">
          Ask follow-up questions about this review and investigation plan.
        </p>
      </div>
      <span className="shrink-0 w-8 h-8 rounded-xl bg-[#FC6D26] text-white flex items-center justify-center shadow-sm">
        <svg
          className="w-4 h-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
          />
        </svg>
      </span>
    </button>
  );
}
