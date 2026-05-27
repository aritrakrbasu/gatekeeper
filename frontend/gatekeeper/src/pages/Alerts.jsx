import React, { useState } from "react";

const Alerts = () => {
  // Dummy data for alerts
  const [alerts, setAlerts] = useState([
    {
      id: "ALT-092",
      severity: "critical",
      type: "Security Vulnerability",
      title: "Critical Prototype Pollution detected",
      repo: "backend-api",
      description:
        "Gatekeeper halted a merge request containing a known prototype pollution vector in the user-settings object mapping.",
      time: "12m ago",
      unread: true,
      action: "Review Blocked MR",
    },
    {
      id: "ALT-091",
      severity: "critical",
      type: "Policy Violation",
      title: "Coverage dropped below 90% threshold",
      repo: "frontend-web",
      description:
        "Recent merge by alex_m bypassed standard review and dropped global test coverage to 88.4%. Auto-deploy has been suspended.",
      time: "1h ago",
      unread: true,
      action: "View Metrics",
    },
    {
      id: "ALT-090",
      severity: "warning",
      type: "Performance Degradation",
      title: "Slow query introduced in active MR",
      repo: "billing-service",
      description:
        "Static analysis predicts a 400ms query time increase on the invoices table due to a missing compound index.",
      time: "3h ago",
      unread: false,
      action: "View AI Fix",
    },
    {
      id: "ALT-089",
      severity: "info",
      type: "System Notice",
      title: "GitLab Webhook synchronization delayed",
      repo: "System",
      description:
        "We detected a 45-second latency spike in receiving webhook payloads from GitLab. Service has since stabilized.",
      time: "Yesterday",
      unread: false,
      action: "View Status",
    },
    {
      id: "ALT-088",
      severity: "warning",
      type: "Technical Debt",
      title: "High cyclomatic complexity",
      repo: "data-pipeline",
      description:
        "The newly added DataTransformer class has a complexity score of 24. Refactoring is recommended.",
      time: "Yesterday",
      unread: false,
      action: "Investigate",
    },
  ]);

  const [activeTab, setActiveTab] = useState("All");

  // Stats derived from alerts
  const criticalCount = alerts.filter((a) => a.severity === "critical").length;
  const warningCount = alerts.filter((a) => a.severity === "warning").length;
  const unreadCount = alerts.filter((a) => a.unread).length;

  const dismissAlert = (id) => {
    setAlerts(alerts.filter((alert) => alert.id !== id));
  };

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case "critical":
        return (
          <div className="w-10 h-10 rounded-xl bg-rose-100/80 border border-rose-200 flex items-center justify-center shrink-0">
            <svg
              className="w-5 h-5 text-rose-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2.5"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
        );
      case "warning":
        return (
          <div className="w-10 h-10 rounded-xl bg-amber-100/80 border border-amber-200 flex items-center justify-center shrink-0">
            <svg
              className="w-5 h-5 text-amber-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2.5"
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
        );
      case "info":
        return (
          <div className="w-10 h-10 rounded-xl bg-blue-100/80 border border-blue-200 flex items-center justify-center shrink-0">
            <svg
              className="w-5 h-5 text-blue-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2.5"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 md:px-8">
      {/* Header & Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">
            Alert Center
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Monitor security threats, policy violations, and system notices.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button className="bg-white/70 hover:bg-white backdrop-blur-xl border border-white/80 text-slate-700 font-medium py-2.5 px-4 rounded-2xl transition-all shadow-sm flex items-center gap-2 text-sm">
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
                d="M5 13l4 4L19 7"
              />
            </svg>
            Mark all as read
          </button>
        </div>
      </div>

      {/* Stats Ribbon */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-slate-900 rounded-[1.5rem] border border-slate-800 p-5 shadow-lg relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-br from-[#FC6D26]/20 to-transparent"></div>
          <p className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-1 relative z-10">
            Total Active
          </p>
          <div className="flex items-end gap-2 relative z-10">
            <p className="text-3xl font-bold text-white">{alerts.length}</p>
            <span className="text-sm text-slate-400 mb-1">
              {unreadCount} unread
            </span>
          </div>
        </div>

        <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm relative overflow-hidden">
          <div className="absolute right-[-10%] top-[-10%] w-24 h-24 bg-rose-500/10 rounded-full blur-xl pointer-events-none"></div>
          <p className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-1 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse"></span>
            Critical
          </p>
          <p className="text-3xl font-bold text-slate-900">
            {criticalCount}
          </p>
        </div>

        <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm">
          <p className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-1 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-500"></span>
            Warnings
          </p>
          <p className="text-3xl font-bold text-slate-900">
            {warningCount}
          </p>
        </div>

        <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm flex flex-col justify-center items-center cursor-pointer hover:bg-white transition-colors">
          <svg
            className="w-6 h-6 text-slate-400 mb-2"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"
            />
          </svg>
          <span className="text-sm font-semibold text-slate-600">
            Alert Settings
          </span>
        </div>
      </div>

      {/* Main Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* LEFT COLUMN: Alerts Feed */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm overflow-hidden flex flex-col h-full min-h-[500px]">
            {/* Tabs */}
            <div className="flex items-center gap-6 px-8 py-5 border-b border-white/80 bg-white/40">
              {["All", "Critical", "Unread"].map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`text-sm font-bold tracking-wide transition-colors ${activeTab === tab ? "text-[#FC6D26]" : "text-slate-400 hover:text-slate-700"}`}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* Alert List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {alerts.map((alert) => (
                <div
                  key={alert.id}
                  className={`group relative p-5 rounded-[1.25rem] transition-all flex flex-col sm:flex-row gap-5 shadow-sm hover:shadow-md hover:-translate-y-0.5 ${
                    alert.unread
                      ? "bg-white border border-white"
                      : "bg-white/40 border border-white/60 opacity-80 hover:opacity-100"
                  }`}
                >
                  {/* Unread Indicator */}
                  {alert.unread && (
                    <div className="absolute left-3 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-[#FC6D26]"></div>
                  )}

                  {/* Icon */}
                  <div className="pl-2 sm:pl-4">
                    {getSeverityIcon(alert.severity)}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                        {alert.type}
                      </span>
                      <span className="text-slate-300">•</span>
                      <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                        {alert.time}
                      </span>
                    </div>
                    <h3
                      className={`text-base font-bold mb-1.5 truncate ${alert.unread ? "text-slate-900" : "text-slate-700"}`}
                    >
                      {alert.title}
                    </h3>
                    <p className="text-sm text-slate-500 leading-relaxed mb-4 line-clamp-2">
                      {alert.description}
                    </p>

                    {/* Meta Tags & Repo */}
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-100 border border-slate-200 text-xs font-mono text-slate-600">
                        <svg
                          className="w-3.5 h-3.5 text-slate-400"
                          viewBox="0 0 24 24"
                          fill="currentColor"
                        >
                          <path d="M23.955 13.587l-1.342-4.135-2.664-8.189c-.135-.423-.73-.423-.867 0L16.418 9.45H7.582L4.919 1.263c-.137-.423-.733-.423-.868 0L1.387 9.452.045 13.587c-.121.374.016.786.335 1.018l11.62 8.442 11.62-8.442c.319-.232.456-.644.335-1.018z" />
                        </svg>
                        {alert.repo}
                      </div>
                      <span className="text-xs text-slate-400 font-medium">
                        {alert.id}
                      </span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex sm:flex-col items-center sm:items-end justify-between sm:justify-center gap-3 border-t sm:border-t-0 sm:border-l border-slate-100 pt-4 sm:pt-0 sm:pl-5">
                    <button
                      className={`w-full sm:w-auto px-4 py-2 rounded-xl text-sm font-semibold transition-all shadow-sm flex items-center justify-center gap-2 ${
                        alert.severity === "critical"
                          ? "bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200"
                          : "bg-slate-900 hover:bg-slate-800 text-white"
                      }`}
                    >
                      {alert.action}
                    </button>
                    <button
                      onClick={() => dismissAlert(alert.id)}
                      className="w-full sm:w-auto px-4 py-2 rounded-xl text-sm font-medium text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition-colors"
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              ))}

              {alerts.length === 0 && (
                <div className="flex flex-col items-center justify-center h-64 text-center">
                  <div className="w-16 h-16 bg-emerald-50 text-emerald-500 rounded-full flex items-center justify-center mb-4">
                    <svg
                      className="w-8 h-8"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                  </div>
                  <h3 className="text-lg font-bold text-slate-900 mb-1">
                    Inbox Zero
                  </h3>
                  <p className="text-sm text-slate-500 max-w-sm">
                    You've cleared all your active alerts. Gatekeeper is
                    actively monitoring your repositories.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Insights & Affected Repos */}
        <div className="flex flex-col gap-6">
          {/* Hotspots Card */}
          <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 lg:p-8">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-bold text-slate-900">
                Vulnerability Hotspots
              </h3>
              <svg
                className="w-5 h-5 text-slate-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
                />
              </svg>
            </div>

            <div className="space-y-5">
              <div>
                <div className="flex justify-between items-end mb-2">
                  <div className="flex items-center gap-2">
                    <svg
                      className="w-4 h-4 text-[#FC6D26]"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                    >
                      <path d="M23.955 13.587l-1.342-4.135-2.664-8.189c-.135-.423-.73-.423-.867 0L16.418 9.45H7.582L4.919 1.263c-.137-.423-.733-.423-.868 0L1.387 9.452.045 13.587c-.121.374.016.786.335 1.018l11.62 8.442 11.62-8.442c.319-.232.456-.644.335-1.018z" />
                    </svg>
                    <span className="text-sm font-semibold text-slate-900">
                      backend-api
                    </span>
                  </div>
                  <span className="text-xs font-bold text-rose-500">
                    2 Critical
                  </span>
                </div>
                <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                  <div className="bg-rose-500 w-3/4 h-full rounded-full"></div>
                </div>
              </div>

              <div>
                <div className="flex justify-between items-end mb-2">
                  <div className="flex items-center gap-2">
                    <svg
                      className="w-4 h-4 text-[#FC6D26]"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                    >
                      <path d="M23.955 13.587l-1.342-4.135-2.664-8.189c-.135-.423-.73-.423-.867 0L16.418 9.45H7.582L4.919 1.263c-.137-.423-.733-.423-.868 0L1.387 9.452.045 13.587c-.121.374.016.786.335 1.018l11.62 8.442 11.62-8.442c.319-.232.456-.644.335-1.018z" />
                    </svg>
                    <span className="text-sm font-semibold text-slate-900">
                      frontend-web
                    </span>
                  </div>
                  <span className="text-xs font-bold text-amber-500">
                    1 Warning
                  </span>
                </div>
                <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                  <div className="bg-amber-400 w-1/3 h-full rounded-full"></div>
                </div>
              </div>

              <div>
                <div className="flex justify-between items-end mb-2">
                  <div className="flex items-center gap-2">
                    <svg
                      className="w-4 h-4 text-[#FC6D26]"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                    >
                      <path d="M23.955 13.587l-1.342-4.135-2.664-8.189c-.135-.423-.73-.423-.867 0L16.418 9.45H7.582L4.919 1.263c-.137-.423-.733-.423-.868 0L1.387 9.452.045 13.587c-.121.374.016.786.335 1.018l11.62 8.442 11.62-8.442c.319-.232.456-.644.335-1.018z" />
                    </svg>
                    <span className="text-sm font-semibold text-slate-900">
                      billing-service
                    </span>
                  </div>
                  <span className="text-xs font-bold text-slate-500">
                    Healthy
                  </span>
                </div>
                <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                  <div className="bg-emerald-400 w-full h-full rounded-full"></div>
                </div>
              </div>
            </div>
          </div>

          {/* Weekly Trend Card (Dark Bento) */}
          <div className="bg-slate-900 rounded-[2rem] border border-slate-800 shadow-xl p-6 lg:p-8 relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-[#FC6D26]/10 to-transparent"></div>
            <div
              className="absolute inset-0 opacity-10"
              style={{
                backgroundImage: `radial-gradient(circle at 1px 1px, white 1px, transparent 0)`,
                backgroundSize: "16px 16px",
              }}
            ></div>

            <h3 className="text-white font-bold text-sm tracking-widest uppercase mb-6 relative z-10">
              7-Day Threat Vector
            </h3>

            {/* Abstract Bar Chart */}
            <div className="flex items-end justify-between h-32 gap-2 relative z-10">
              <div className="w-full bg-slate-800 rounded-t-sm h-[30%] hover:bg-slate-700 transition-colors"></div>
              <div className="w-full bg-slate-800 rounded-t-sm h-[45%] hover:bg-slate-700 transition-colors"></div>
              <div className="w-full bg-[#FC6D26] rounded-t-sm h-[80%] shadow-[0_0_15px_rgba(252,109,38,0.5)]"></div>
              <div className="w-full bg-slate-800 rounded-t-sm h-[20%] hover:bg-slate-700 transition-colors"></div>
              <div className="w-full bg-slate-800 rounded-t-sm h-[35%] hover:bg-slate-700 transition-colors"></div>
              <div className="w-full bg-slate-800 rounded-t-sm h-[10%] hover:bg-slate-700 transition-colors"></div>
              <div className="w-full bg-slate-800 rounded-t-sm h-[15%] hover:bg-slate-700 transition-colors"></div>
            </div>

            <div className="flex justify-between text-[10px] text-slate-500 font-mono mt-3 relative z-10">
              <span>Mon</span>
              <span>Tue</span>
              <span className="text-[#FC6D26] font-bold">Wed</span>
              <span>Thu</span>
              <span>Fri</span>
              <span>Sat</span>
              <span>Sun</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Alerts;
