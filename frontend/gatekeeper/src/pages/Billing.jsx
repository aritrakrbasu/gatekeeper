import React from "react";
import { useBillingUsage, useInvoices } from "../services/queries";

/**
 * Helper to format token numbers (e.g., 4200000 -> "4.2M")
 */
function formatTokens(tokens) {
  if (!tokens || tokens === 0) return "0";
  if (tokens >= 1_000_000) {
    return `${(tokens / 1_000_000).toFixed(1)}M`;
  } else if (tokens >= 1_000) {
    return `${(tokens / 1_000).toFixed(1)}K`;
  }
  return tokens.toString();
}

/**
 * Format model name for display
 */
function formatModelName(modelName) {
  const modelNames = {
    "gemini-3.5-flash": "Gemini 3.5 Flash",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview",
    "gemini-1.5-pro": "Gemini 1.5 Pro",
    "gemini-1.5-flash": "Gemini 1.5 Flash",
  };
  return modelNames[modelName] || modelName;
}

/**
 * Calculate percentage of total
 */
function calculatePercentage(value, total) {
  if (!total || total === 0) return 0;
  return Math.round((value / total) * 100);
}

/**
 * Format billing cycle dates
 */
function formatBillingCycle(startDate, endDate) {
  try {
    const start = new Date(startDate);
    const end = new Date(endDate);
    const months = [
      "Jan",
      "Feb",
      "Mar",
      "Apr",
      "May",
      "Jun",
      "Jul",
      "Aug",
      "Sep",
      "Oct",
      "Nov",
      "Dec",
    ];
    return `${months[start.getMonth()]} ${start.getDate()} - ${months[end.getMonth()]} ${end.getDate()}, ${end.getFullYear()}`;
  } catch {
    return "Current Month";
  }
}

/**
 * Format invoice date
 */
function formatInvoiceDate(dateStr) {
  try {
    const date = new Date(dateStr);
    const months = [
      "Jan",
      "Feb",
      "Mar",
      "Apr",
      "May",
      "Jun",
      "Jul",
      "Aug",
      "Sep",
      "Oct",
      "Nov",
      "Dec",
    ];
    return `${months[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
  } catch {
    return dateStr;
  }
}

const Billing = () => {
  // Fetch billing data from API
  const {
    data: billingData,
    isLoading: billingLoading,
    error: billingError,
  } = useBillingUsage();
  const { data: invoices = [], isLoading: invoicesLoading } = useInvoices();

  // Show loading state
  if (billingLoading) {
    return (
      <div className="relative h-screen bg-[#F2F4F7] font-sans text-slate-900 overflow-hidden flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#FC6D26]"></div>
      </div>
    );
  }

  // Show error state
  if (billingError) {
    return (
      <div className="relative h-screen bg-[#F2F4F7] font-sans text-slate-900 overflow-hidden flex items-center justify-center">
        <div className="bg-red-50 border border-red-200 rounded-2xl p-6 flex items-center gap-3">
          <svg
            className="w-6 h-6 text-red-500"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <div>
            <p className="font-semibold text-red-800">
              Failed to load usage data
            </p>
            <p className="text-sm text-red-600">Please try again later.</p>
          </div>
        </div>
      </div>
    );
  }

  // Extract data from API response
  const billingCycle =
    billingData?.current_cycle_start && billingData?.current_cycle_end
      ? formatBillingCycle(
          billingData.current_cycle_start,
          billingData.current_cycle_end,
        )
      : "Current Month";

  const totalCost = billingData?.estimated_cost || 0;
  const projectedTotal = totalCost * 1.2; // 20% projection

  const usageStats = {
    currentTotal: `$${totalCost.toFixed(2)}`,
    projectedTotal: `$${projectedTotal.toFixed(2)}`,
    totalTokens: formatTokens(billingData?.total_tokens || 0),
    mrsProcessed: billingData?.total_mrs_processed || 0,
  };

  // Map model_usage to geminiBreakdown format
  const geminiBreakdown = (billingData?.model_usage || []).map((model) => ({
    model: formatModelName(model.model_name),
    inputTokens: formatTokens(model.input_tokens),
    outputTokens: formatTokens(model.output_tokens),
    cost: `$${model.estimated_cost.toFixed(2)}`,
    percentage: calculatePercentage(model.estimated_cost, totalCost),
  }));

  // If no breakdown data, show empty state
  if (geminiBreakdown.length === 0) {
    geminiBreakdown.push({
      model: "No usage yet",
      inputTokens: "0",
      outputTokens: "0",
      cost: "$0.00",
      percentage: 0,
    });
  }

  // Map invoices to display format
  const recentInvoices = (invoices || []).map((inv) => ({
    date: formatInvoiceDate(inv.invoice_date),
    amount: `$${inv.amount.toFixed(2)}`,
    status:
      inv.status === "paid"
        ? "Paid"
        : inv.status === "pending"
          ? "Pending"
          : "Failed",
    invoiceId: inv.invoice_number || `INV-${inv.id}`,
  }));

  // Add dummy invoices if none exist (for demo purposes)
  if (recentInvoices.length === 0) {
    recentInvoices.push({
      date: "No logs yet",
      amount: "$0.00",
      status: "Pending",
      invoiceId: "LOG-PENDING",
    });
  }

  // Dynamic chart data from API daily_usage
  const chartData = (billingData?.daily_usage || []).map((day) =>
    day.tokens > 0 ? Math.round(day.tokens / 100_000) : 0,
  );
  const maxChartVal = Math.max(...chartData, 1);

  return (
    <div className="relative h-screen bg-[#F2F4F7] font-sans text-slate-900 overflow-hidden selection:bg-[#FC6D26] selection:text-white">
      {/* Ambient Background Glows */}
      <div className="absolute top-[-10%] left-[-10%] w-[40rem] h-[40rem] bg-indigo-500/10 rounded-full blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[40rem] h-[40rem] bg-[#FC6D26]/5 rounded-full blur-[120px] pointer-events-none"></div>

      {/* =========================================
          MAIN CONTENT AREA
          ========================================= */}
      <main className="h-full overflow-y-auto overflow-x-hidden w-full pt-8 md:pt-10 pb-28 md:pb-10 relative z-10">
        <div className="max-w-6xl mx-auto px-4 md:px-8">
          {/* Header & Notice */}
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-8">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <h1 className="text-3xl font-bold text-slate-900 tracking-tight">
                  API Usage & Estimates
                </h1>
                <span className="px-2.5 py-1 bg-emerald-100 text-emerald-700 text-[10px] font-bold uppercase tracking-widest rounded-full border border-emerald-200">
                  Gatekeeper is Free
                </span>
              </div>
              <p className="text-sm text-slate-500">
                Current cycle:{" "}
                <span className="font-medium text-slate-700">
                  {billingCycle}
                </span>
              </p>
            </div>
          </div>

          {/* Top Metrics Ribbon */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-6">
            {/* Dark Card emphasizing Google's estimated cost */}
            <div className="bg-slate-950 rounded-[1.5rem] border border-slate-800 p-5 shadow-lg relative overflow-hidden group">
              <div className="absolute inset-0 bg-gradient-to-br from-[#FC6D26]/20 to-transparent"></div>
              <p className="text-slate-400 text-[10px] font-bold uppercase tracking-widest mb-1 relative z-10">
                Est. Google API Cost
              </p>
              <div className="flex items-baseline gap-1 relative z-10">
                <p className="text-4xl font-light text-white tracking-tighter">
                  {usageStats.currentTotal}
                </p>
              </div>
              <p className="text-[10px] text-slate-500 mt-2 font-medium relative z-10">
                Projected: {usageStats.projectedTotal}
              </p>
            </div>

            {/* Clear contrast for the Free Platform */}
            <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm">
              <p className="text-slate-500 text-[10px] font-bold uppercase tracking-widest mb-1">
                Gatekeeper Platform Fee
              </p>
              <p className="text-4xl font-light text-emerald-600 tracking-tighter">
                $0.00
              </p>
              <p className="text-[10px] text-emerald-600/70 font-bold uppercase tracking-widest mt-2">
                Free Forever
              </p>
            </div>

            <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm">
              <p className="text-slate-500 text-[10px] font-bold uppercase tracking-widest mb-1">
                Tokens Processed
              </p>
              <p className="text-4xl font-light text-slate-900 tracking-tighter">
                {usageStats.totalTokens}
              </p>
              <p className="text-[10px] text-slate-400 mt-2 font-medium">
                Combined Context & Generated
              </p>
            </div>

            <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm">
              <p className="text-slate-500 text-[10px] font-bold uppercase tracking-widest mb-1">
                MRs Reviewed
              </p>
              <p className="text-4xl font-light text-slate-900 tracking-tighter">
                {usageStats.mrsProcessed}
              </p>
              <p className="text-[10px] text-slate-400 mt-2 font-medium">
                Automated by Gatekeeper
              </p>
            </div>
          </div>

          {/* Main Grid Layout */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* LEFT COLUMN: Charts & Logs (Spans 2 columns) */}
            <div className="lg:col-span-2 flex flex-col gap-6">
              {/* Token Usage Over Time Chart */}
              <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 lg:p-8">
                <div className="flex justify-between items-center mb-6">
                  <h3 className="text-lg font-bold text-slate-900">
                    Token Usage History (14 Days)
                  </h3>
                  <div className="flex items-center gap-2 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                    <div className="w-2 h-2 rounded-full bg-[#FC6D26]"></div>{" "}
                    Tokens
                  </div>
                </div>

                <div className="h-48 flex items-end justify-between gap-1 sm:gap-2 pt-4 border-b border-slate-200 pb-2">
                  {chartData.map((val, idx) => {
                    const actualTokens =
                      billingData?.daily_usage?.[idx]?.tokens || 0;
                    return (
                      <div
                        key={idx}
                        className="w-full relative group flex flex-col items-center justify-end h-full"
                      >
                        <div className="opacity-0 group-hover:opacity-100 absolute -top-8 bg-slate-900 text-white text-[10px] px-2 py-1 rounded transition-opacity whitespace-nowrap z-10 pointer-events-none shadow-md">
                          {formatTokens(actualTokens)} tokens
                        </div>
                        <div
                          className="w-full bg-[#FC6D26]/20 hover:bg-[#FC6D26] rounded-t-md transition-all duration-300 relative overflow-hidden"
                          style={{ height: `${(val / maxChartVal) * 100}%` }}
                        >
                          <div
                            className="absolute bottom-0 w-full bg-[#FC6D26] opacity-50"
                            style={{ height: "30%" }}
                          ></div>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="flex justify-between text-[10px] font-bold text-slate-400 mt-3 uppercase tracking-widest">
                  <span>14 Days Ago</span>
                  <span>7 Days Ago</span>
                  <span>Today</span>
                </div>
              </div>

              {/* Usage Reports List (Replaces "Invoices") */}
              <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 lg:p-8">
                <div className="flex justify-between items-center mb-5">
                  <h3 className="text-lg font-bold text-slate-900">
                    Usage Snapshots
                  </h3>
                  <p className="text-xs font-medium text-slate-400">
                    Historical API estimates
                  </p>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-slate-200">
                        <th className="pb-3 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                          Date
                        </th>
                        <th className="pb-3 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                          Report ID
                        </th>
                        <th className="pb-3 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                          Est. Amount
                        </th>
                        <th className="pb-3 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                          Status
                        </th>
                        <th className="pb-3 text-[10px] font-bold text-slate-400 uppercase tracking-wider text-right">
                          Log
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {recentInvoices.map((inv, idx) => (
                        <tr
                          key={idx}
                          className="hover:bg-white/50 transition-colors group"
                        >
                          <td className="py-4 text-sm font-semibold text-slate-900">
                            {inv.date}
                          </td>
                          <td className="py-4 text-xs font-mono text-slate-500">
                            {inv.invoiceId}
                          </td>
                          <td className="py-4 text-sm font-bold text-slate-900">
                            {inv.amount}
                          </td>
                          <td className="py-4">
                            <span
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-widest ${
                                inv.status === "Paid"
                                  ? "bg-slate-100 text-slate-600 border border-slate-200"
                                  : inv.status === "Pending"
                                    ? "bg-amber-50 text-amber-600 border border-amber-100"
                                    : "bg-red-50 text-red-600 border border-red-100"
                              }`}
                            >
                              {inv.status === "Paid" ? "Logged" : inv.status}
                            </span>
                          </td>
                          <td className="py-4 text-right">
                            <button className="text-slate-400 hover:text-[#FC6D26] transition-colors p-1">
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
                                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                                />
                              </svg>
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* RIGHT COLUMN: Gemini Model Breakdown */}
            <div className="flex flex-col gap-6">
              <div className="bg-slate-950 rounded-[2rem] border border-slate-800 shadow-xl p-6 lg:p-8 relative overflow-hidden group">
                <div className="absolute inset-0 bg-gradient-to-br from-[#FC6D26]/10 to-transparent"></div>
                <div
                  className="absolute inset-0 opacity-10"
                  style={{
                    backgroundImage: `radial-gradient(circle at 1px 1px, white 1px, transparent 0)`,
                    backgroundSize: "16px 16px",
                  }}
                ></div>

                <div className="relative z-10 flex items-center gap-2 mb-8 border-b border-slate-800/80 pb-5">
                  <svg
                    className="w-5 h-5 text-[#FC6D26]"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"
                    />
                  </svg>
                  <h3 className="text-white font-bold text-sm tracking-widest uppercase">
                    Gemini Breakdown
                  </h3>
                </div>

                <div className="relative z-10 space-y-6">
                  {geminiBreakdown.map((item, idx) => (
                    <div
                      key={idx}
                      className="border-b border-slate-800/80 pb-5 last:border-0 last:pb-0"
                    >
                      <div className="flex justify-between items-start mb-4">
                        <div>
                          <h4 className="text-sm font-bold text-slate-200">
                            {item.model}
                          </h4>
                          <span className="text-[9px] font-bold text-slate-500 uppercase tracking-widest">
                            {item.percentage}% of total usage
                          </span>
                        </div>
                        <span className="text-lg font-light text-[#FC6D26] tracking-tight">
                          {item.cost}
                        </span>
                      </div>

                      <div className="space-y-3">
                        <div>
                          <div className="flex justify-between text-[10px] font-mono text-slate-400 mb-1.5">
                            <span>Input (Context)</span>
                            <span className="text-white">
                              {item.inputTokens}
                            </span>
                          </div>
                          <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden">
                            <div
                              className="bg-slate-400 h-full rounded-full"
                              style={{
                                width: item.percentage
                                  ? `${item.percentage}%`
                                  : "0%",
                              }}
                            ></div>
                          </div>
                        </div>
                        <div>
                          <div className="flex justify-between text-[10px] font-mono text-slate-400 mb-1.5">
                            <span>Output (Generated)</span>
                            <span className="text-white">
                              {item.outputTokens}
                            </span>
                          </div>
                          <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden">
                            <div
                              className="bg-emerald-400 h-full rounded-full"
                              style={{
                                width: item.percentage
                                  ? `${Math.min(item.percentage * 0.6, 100)}%`
                                  : "0%",
                              }}
                            ></div>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="relative z-10 mt-8 pt-5 border-t border-slate-800/80 flex justify-between items-center text-xs">
                  <a
                    href="https://console.cloud.google.com/billing"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-slate-400 hover:text-white transition-colors flex items-center gap-1 font-medium"
                  >
                    Google Cloud Billing
                    <svg
                      className="w-3 h-3"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                      />
                    </svg>
                  </a>
                  <a
                    href="https://ai.google.dev/pricing"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[#FC6D26] hover:text-white transition-colors font-medium"
                  >
                    View Pricing Docs
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Billing;
