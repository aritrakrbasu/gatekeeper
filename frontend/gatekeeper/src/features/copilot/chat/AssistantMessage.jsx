import React from "react";
import { TerminalMarkdown } from "../../../components/shared";

export function AssistantMessage({ content, streaming = false }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[95%] w-full bg-slate-900 rounded-2xl px-4 py-3 shadow-sm">
        {content ? (
          <TerminalMarkdown>{content}</TerminalMarkdown>
        ) : streaming ? (
          <p className="text-slate-500 text-sm italic">Thinking...</p>
        ) : (
          <p className="text-slate-500 text-sm italic">No response yet.</p>
        )}
      </div>
    </div>
  );
}
