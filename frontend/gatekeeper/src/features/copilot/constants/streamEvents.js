/**
 * Copilot SSE event types — mirrors backend StreamEventType enum.
 */
export const STREAM_EVENTS = {
  NODE_STARTED: "node_started",
  NODE_COMPLETED: "node_completed",
  RESPONSE_CHUNK: "response_chunk",
  CHECKPOINT: "checkpoint",
  DONE: "done",
  ERROR: "error",
  KNOWLEDGE_PROPOSED: "knowledge_proposed",
  APPROVAL_REQUIRED: "approval_required",
  PLAN_STEP_COMPLETED: "plan_step_completed",
  INTERRUPTED: "interrupted",
};

export const CONNECTION_STATUS = {
  IDLE: "idle",
  CONNECTING: "connecting",
  CONNECTED: "connected",
  DISCONNECTED: "disconnected",
  ERROR: "error",
};
