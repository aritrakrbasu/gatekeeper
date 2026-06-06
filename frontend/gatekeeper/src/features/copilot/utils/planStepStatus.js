export const PLAN_STEP_STATUS = {
  PENDING: "pending",
  RUNNING: "running",
  COMPLETED: "completed",
  FAILED: "failed",
};

/**
 * Derive investigation plan step status from cursor position and session flags.
 */
export function getPlanStepStatus(stepIndex, stepCursor, { isStreaming, status } = {}) {
  if (stepIndex < stepCursor) {
    return PLAN_STEP_STATUS.COMPLETED;
  }

  if (stepIndex === stepCursor) {
    if (status === "failed") {
      return PLAN_STEP_STATUS.FAILED;
    }
    if (isStreaming || status === "running" || status === "waiting_approval") {
      return PLAN_STEP_STATUS.RUNNING;
    }
  }

  return PLAN_STEP_STATUS.PENDING;
}

export function getPlanStepStatusClass(stepStatus) {
  switch (stepStatus) {
    case PLAN_STEP_STATUS.RUNNING:
      return "border-blue-300 bg-blue-50 text-blue-700";
    case PLAN_STEP_STATUS.COMPLETED:
      return "border-emerald-300 bg-emerald-50 text-emerald-700";
    case PLAN_STEP_STATUS.FAILED:
      return "border-rose-300 bg-rose-50 text-rose-700";
    default:
      return "border-slate-200 bg-slate-50 text-slate-600";
  }
}
