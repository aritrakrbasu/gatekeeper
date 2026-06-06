import React from "react";

/**
 * Maps log status to terminal text color classes.
 */
export function getLogStatusClass(status) {
  if (status === "running") return "text-blue-400";
  if (status === "completed") return "text-emerald-400";
  if (status === "failed") return "text-rose-400";
  return "text-slate-300";
}

/**
 * Formats a log timestamp for display (HH:MM:SS).
 */
export function formatLogTimestamp(timestamp) {
  return new Date(timestamp).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/**
 * Generic timestamped activity log panel.
 * Extracted from RepoDetails ProgressLogsViewer rendering.
 */
export function ActivityLog({
  logs = [],
  isLoading = false,
  isLive = false,
  title = "Analysis Progress",
  emptyReturnNull = true,
  maxHeightClass = "max-h-48",
}) {
  if (logs.length === 0 && !isLoading && emptyReturnNull) {
    return null;
  }

  return (
    <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden">
      <div className="px-4 py-3 bg-slate-800/50 border-b border-slate-700/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isLive && (
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          )}
          <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
            {title}
          </span>
        </div>
        {isLive && (
          <span className="text-[10px] text-blue-400 font-medium">Live</span>
        )}
      </div>
      <div
        className={`p-4 ${maxHeightClass} overflow-y-auto space-y-2 font-mono text-xs`}
      >
        {logs.map((log, idx) => (
          <div key={idx} className="flex items-start gap-2">
            <span className="text-slate-500 shrink-0">
              {formatLogTimestamp(log.timestamp)}
            </span>
            <span className={`flex-1 ${getLogStatusClass(log.status)}`}>
              {log.message}
            </span>
          </div>
        ))}
        {isLoading && (
          <div className="text-slate-500 text-center py-2">Loading logs...</div>
        )}
      </div>
    </div>
  );
}
