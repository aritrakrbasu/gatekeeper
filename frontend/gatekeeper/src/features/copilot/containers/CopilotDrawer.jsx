import React from "react";
import { GlassDrawer } from "../../../components/shared";
import { CopilotWorkspace } from "./CopilotWorkspace";

export function CopilotDrawer({
  isOpen,
  onClose,
  repositoryId,
  mrIid,
  conversationId,
  mrTitle,
}) {
  return (
    <GlassDrawer isOpen={isOpen} onClose={onClose} zIndex="z-[110]">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between bg-white/50 shrink-0">
        <div className="min-w-0">
          <h2 className="text-sm font-bold text-slate-900 truncate">
            Engineering Copilot
          </h2>
          {mrTitle && (
            <p className="text-xs text-slate-500 truncate">{mrTitle}</p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 hover:bg-slate-200 hover:text-slate-900 transition-colors shrink-0"
          aria-label="Close copilot drawer"
        >
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
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>

      <CopilotWorkspace
        repositoryId={repositoryId}
        mrIid={mrIid}
        conversationId={conversationId}
        enabled={isOpen}
      />
    </GlassDrawer>
  );
}
