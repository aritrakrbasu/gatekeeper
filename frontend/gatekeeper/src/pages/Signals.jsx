import { useMemo, useState } from "react";
import {
  useAlerts,
  useDismissAlert,
  useMarkAlertRead,
  useMarkAllAlertsRead,
} from "../services/queries";

const SENTRY_SOURCE = "sentry";

const severityStyles = {
  critical: "bg-red-50 text-red-700 border-red-100",
  warning: "bg-amber-50 text-amber-700 border-amber-100",
  info: "bg-sky-50 text-sky-700 border-sky-100",
};

function SeverityBadge({ severity }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${
        severityStyles[severity] || severityStyles.info
      }`}
    >
      {severity}
    </span>
  );
}

const Signals = () => {
  const [severityFilter, setSeverityFilter] = useState("all");

  const { data: alerts = [], isLoading, error } = useAlerts({
    source: SENTRY_SOURCE,
    severity: severityFilter === "all" ? undefined : severityFilter,
  });
  const markReadMutation = useMarkAlertRead();
  const dismissMutation = useDismissAlert();
  const markAllReadMutation = useMarkAllAlertsRead(SENTRY_SOURCE);

  const unreadCount = useMemo(
    () => alerts.filter((alert) => alert.unread).length,
    [alerts],
  );

  const handleOpen = async (alert) => {
    if (alert.unread) {
      await markReadMutation.mutateAsync(alert.id);
    }
    if (alert.web_url) {
      window.open(alert.web_url, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 md:px-8 pb-10">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
        <div>
          <p className="text-sm font-medium text-[#FC6D26] mb-2">Alerts</p>
          <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">
            Production Errors
          </h1>
          <p className="text-slate-600 text-sm mt-2 max-w-2xl">
            Sentry issues from your connected repositories, synced from webhook
            payloads stored in MongoDB.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {unreadCount > 0 && (
            <button
              onClick={() => markAllReadMutation.mutate()}
              disabled={markAllReadMutation.isPending}
              className="px-4 py-2 rounded-2xl bg-white/70 border border-white/80 text-sm font-medium text-slate-700 hover:bg-white transition-all"
            >
              Mark all read
            </button>
          )}
          <div className="px-4 py-2 rounded-2xl bg-slate-900 text-white text-sm font-medium">
            {unreadCount} unread
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 mb-8">
        {["all", "critical", "warning", "info"].map((level) => (
          <button
            key={level}
            onClick={() => setSeverityFilter(level)}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
              severityFilter === level
                ? "bg-[#FC6D26] text-white shadow-sm"
                : "bg-white/70 text-slate-600 border border-white/80 hover:bg-white"
            }`}
          >
            {level === "all" ? "All severities" : level}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="rounded-[2rem] bg-white/60 border border-white/80 p-10 text-center text-slate-500">
          Loading Sentry issues...
        </div>
      )}

      {error && (
        <div className="rounded-[2rem] bg-red-50 border border-red-100 p-6 text-red-700">
          Failed to load Sentry issues: {error.message}
        </div>
      )}

      {!isLoading && !error && alerts.length === 0 && (
        <div className="rounded-[2rem] bg-white/60 border border-white/80 p-10 text-center">
          <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-4">
            <svg className="w-7 h-7 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-slate-900 mb-2">No Sentry issues yet</h2>
          <p className="text-slate-500 text-sm max-w-md mx-auto">
            Connect Sentry on a repository details page, configure the webhook,
            then trigger a test error in your app.
          </p>
        </div>
      )}

      <div className="space-y-4">
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className={`rounded-[1.75rem] border p-5 md:p-6 transition-all ${
              alert.unread
                ? "bg-white/80 border-[#FC6D26]/20 shadow-[0_8px_32px_rgba(252,109,38,0.08)]"
                : "bg-white/60 border-white/80"
            }`}
          >
            <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2 mb-3">
                  <SeverityBadge severity={alert.severity} />
                  <span className="inline-flex items-center rounded-full bg-purple-50 px-2.5 py-1 text-xs font-medium text-purple-700">
                    Sentry
                  </span>
                  <span className="text-xs text-slate-400">{alert.time}</span>
                  {alert.unread && (
                    <span className="inline-flex h-2 w-2 rounded-full bg-[#FC6D26]" />
                  )}
                </div>

                <h3 className="text-lg font-semibold text-slate-900 mb-1">
                  {alert.title}
                </h3>

                <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500 mb-3">
                  <span>{alert.type}</span>
                  <span>•</span>
                  <span>{alert.repo}</span>
                  {alert.issue_id && (
                    <>
                      <span>•</span>
                      <span>Issue {alert.issue_id}</span>
                    </>
                  )}
                </div>

                <p className="text-sm text-slate-600 leading-relaxed">
                  {alert.description}
                </p>
              </div>

              <div className="flex flex-wrap gap-2 shrink-0">
                <button
                  onClick={() => handleOpen(alert)}
                  className="px-4 py-2 rounded-2xl bg-slate-900 text-white text-sm font-medium hover:bg-slate-800 transition-all"
                >
                  {alert.action || "View in Sentry"}
                </button>
                <button
                  onClick={() => dismissMutation.mutate(alert.id)}
                  disabled={dismissMutation.isPending}
                  className="px-4 py-2 rounded-2xl bg-white border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-all"
                >
                  Dismiss
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default Signals;
