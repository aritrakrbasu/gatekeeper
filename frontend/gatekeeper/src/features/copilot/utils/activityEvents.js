import { STREAM_EVENTS } from "../constants/streamEvents";

function formatActivityMessage(event) {
  const { type, node, data } = event;

  switch (type) {
    case STREAM_EVENTS.NODE_STARTED:
      return `Started ${node ?? data?.node ?? "node"}`;
    case STREAM_EVENTS.NODE_COMPLETED:
      return `Completed ${node ?? data?.node ?? "node"}`;
    case STREAM_EVENTS.APPROVAL_REQUIRED:
      return `Approval required: ${data?.tool_name ?? "tool action"}`;
    case STREAM_EVENTS.INTERRUPTED:
      return "Execution interrupted — approval needed";
    case STREAM_EVENTS.KNOWLEDGE_PROPOSED:
      return `Knowledge proposed (${data?.count ?? data?.proposed_count ?? 0})`;
    case STREAM_EVENTS.PLAN_STEP_COMPLETED:
      return `Plan step completed: ${data?.step_id ?? "step"}`;
    case STREAM_EVENTS.ERROR:
      return data?.message ?? "Stream error";
    default:
      return type?.replace(/_/g, " ") ?? "Activity";
  }
}

function mapActivityStatus(type) {
  if (type === STREAM_EVENTS.NODE_STARTED) return "running";
  if (type === STREAM_EVENTS.NODE_COMPLETED) return "completed";
  if (type === STREAM_EVENTS.ERROR) return "failed";
  if (
    type === STREAM_EVENTS.APPROVAL_REQUIRED ||
    type === STREAM_EVENTS.INTERRUPTED
  ) {
    return "running";
  }
  return "completed";
}

/**
 * Map session activityEvents to ActivityLog log entries.
 */
export function mapActivityEventsToLogs(activityEvents = []) {
  return activityEvents.map((event, index) => ({
    timestamp: event.timestamp ?? new Date().toISOString(),
    status: mapActivityStatus(event.type),
    message: formatActivityMessage(event),
    key: event.id ?? `${event.type}-${index}`,
  }));
}
