import React from "react";

export function StreamingIndicator({ isStreaming }) {
  if (!isStreaming) {
    return null;
  }

  return (
    <div className="flex items-center gap-2 px-1 py-2 text-xs text-blue-600">
      <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
      <span className="font-medium">Copilot is responding...</span>
    </div>
  );
}
