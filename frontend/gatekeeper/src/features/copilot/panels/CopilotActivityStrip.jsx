import React from "react";
import { ActivityLog } from "../../../components/shared";
import { mapActivityEventsToLogs } from "../utils/activityEvents";

export function CopilotActivityStrip({ activityEvents = [], isStreaming = false }) {
  const logs = mapActivityEventsToLogs(activityEvents);

  if (logs.length === 0) {
    return null;
  }

  return (
    <div className="px-4 py-2 border-b border-slate-100">
      <ActivityLog
        logs={logs}
        isLive={isStreaming}
        title="Copilot Activity"
        emptyReturnNull
        maxHeightClass="max-h-28"
      />
    </div>
  );
}
