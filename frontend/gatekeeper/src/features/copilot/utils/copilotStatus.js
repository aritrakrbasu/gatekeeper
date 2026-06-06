const STATUS_STYLES = {
  running: "bg-blue-100 text-blue-700 border-blue-200",
  waiting_approval: "bg-amber-100 text-amber-700 border-amber-200",
  completed: "bg-emerald-100 text-emerald-700 border-emerald-200",
  failed: "bg-rose-100 text-rose-700 border-rose-200",
};

const STATUS_LABELS = {
  running: "Running",
  waiting_approval: "Awaiting Approval",
  completed: "Completed",
  failed: "Failed",
};

export function getCopilotStatusLabel(status) {
  return STATUS_LABELS[status] ?? status ?? "Unknown";
}

export function getCopilotStatusClass(status) {
  return STATUS_STYLES[status] ?? "bg-slate-100 text-slate-700 border-slate-200";
}
