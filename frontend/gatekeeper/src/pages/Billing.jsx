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
        <div className="text-slate-500">Loading billing data...</div>
      </div>
    );
  }

  // Show error state
  if (billingError) {
    return (
      <div className="relative h-screen bg-[#F2F4F7] font-sans text-slate-900 overflow-hidden flex items-center justify-center">
        <div className="text-red-500">
          Failed to load billing data. Please try again.
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
      date: "No invoices yet",
      amount: "$0.00",
      status: "Pending",
      invoiceId: "INV-PENDING",
    });
  }

  // Dynamic chart data from API daily_usage
  // Convert tokens to chart units (1 unit = 100k tokens for display)
  const chartData = (billingData?.daily_usage || []).map((day) =>
    day.tokens > 0 ? Math.round(day.tokens / 100_000) : 0,
  );
  const maxChartVal = Math.max(...chartData, 1); // Minimum 1 to avoid division by zero

  return (
    <div className="relative h-screen bg-[#F2F4F7] font-sans text-slate-900 overflow-hidden selection:bg-[#FC6D26] selection:text-white">
      {/* Ambient Background Glows */}
      <div className="absolute top-[-10%] left-[-10%] w-[40rem] h-[40rem] bg-indigo-500/10 rounded-full blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[40rem] h-[40rem] bg-[#FC6D26]/5 rounded-full blur-[120px] pointer-events-none"></div>

      {/* =========================================
          MAIN CONTENT AREA
          ========================================= */}
      <main className="h-full overflow-y-auto overflow-x-hidden w-full pt-10 md:pt-6 pb-28 md:pb-6 relative z-10">
        <div className="max-w-6xl mx-auto px-4 md:px-8">
          {/* Header & Actions */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
            <div>
              <h1 className="text-3xl font-bold text-slate-900 tracking-tight">
                Billing & Usage
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                Current cycle:{" "}
                <span className="font-medium text-slate-700">
                  {billingCycle}
                </span>
              </p>
            </div>

            <div className="flex items-center gap-3">
              <button className="bg-slate-900 hover:bg-slate-800 text-white font-medium py-2.5 px-5 rounded-2xl transition-all shadow-md flex items-center gap-2 text-sm">
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
                Download Invoice
              </button>
            </div>
          </div>

          {/* Top Metrics Ribbon */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm relative overflow-hidden">
              <p className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-1">
                Current Bill
              </p>
              <div className="flex items-baseline gap-1">
                <p className="text-3xl font-bold text-slate-900">
                  {usageStats.currentTotal}
                </p>
                <span className="text-sm text-slate-400 font-medium">USD</span>
              </div>
              <p className="text-xs text-slate-400 mt-2">
                Projected: {usageStats.projectedTotal}
              </p>
            </div>

            <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm">
              <p className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-1">
                Total Tokens Processed
              </p>
              <p className="text-3xl font-bold text-[#FC6D26]">
                {usageStats.totalTokens}
              </p>
              <p className="text-xs text-slate-400 mt-2">
                Across all Gemini models
              </p>
            </div>

            <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm">
              <p className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-1">
                MRs Reviewed
              </p>
              <p className="text-3xl font-bold text-slate-900">
                {usageStats.mrsProcessed}
              </p>
              <p className="text-xs text-emerald-500 font-medium mt-2 flex items-center gap-1">
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
                    d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
                  />
                </svg>
                Auto-tracked
              </p>
            </div>

            <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm flex flex-col justify-between">
              <p className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-1">
                Gatekeeper Plan
              </p>
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-1 bg-slate-900 text-white text-xs font-bold rounded-lg uppercase tracking-wider">
                  Pay-as-you-go
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-2">
                Based on actual usage
              </p>
            </div>
          </div>

          {/* Main Grid Layout */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* LEFT COLUMN: Charts & Breakdown (Spans 2 columns) */}
            <div className="lg:col-span-2 flex flex-col gap-6">
              {/* Token Usage Over Time Chart */}
              <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 lg:p-8">
                <div className="flex justify-between items-center mb-6">
                  <h3 className="text-lg font-bold text-slate-900">
                    API Usage History (14 Days)
                  </h3>
                  <div className="flex items-center gap-4 text-xs font-medium">
                    <span className="flex items-center gap-1.5 text-slate-500">
                      <div className="w-2 h-2 rounded-full bg-[#FC6D26]"></div>{" "}
                      Tokens
                    </span>
                  </div>
                </div>

                {/* CSS Simulated Bar Chart */}
                <div className="h-48 flex items-end justify-between gap-1 sm:gap-2 pt-4 border-b border-slate-200 pb-2">
                  {chartData.map((val, idx) => {
                    // Get actual token count from daily_usage for tooltip
                    const actualTokens =
                      billingData?.daily_usage?.[idx]?.tokens || 0;
                    return (
                      <div
                        key={idx}
                        className="w-full relative group flex flex-col items-center justify-end h-full"
                      >
                        {/* Tooltip on hover */}
                        <div className="opacity-0 group-hover:opacity-100 absolute -top-8 bg-slate-900 text-white text-[10px] px-2 py-1 rounded transition-opacity whitespace-nowrap z-10 pointer-events-none">
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
                <div className="flex justify-between text-[10px] font-bold text-slate-400 mt-2 uppercase tracking-widest">
                  <span>14 Days Ago</span>
                  <span>7 Days Ago</span>
                  <span>Today</span>
                </div>
              </div>

              {/* Invoices List */}
              <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 lg:p-8">
                <div className="flex justify-between items-center mb-5">
                  <h3 className="text-lg font-bold text-slate-900">
                    Recent Invoices
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-slate-200">
                        <th className="pb-3 text-xs font-bold text-slate-400 uppercase tracking-wider">
                          Date
                        </th>
                        <th className="pb-3 text-xs font-bold text-slate-400 uppercase tracking-wider">
                          Invoice ID
                        </th>
                        <th className="pb-3 text-xs font-bold text-slate-400 uppercase tracking-wider">
                          Amount
                        </th>
                        <th className="pb-3 text-xs font-bold text-slate-400 uppercase tracking-wider">
                          Status
                        </th>
                        <th className="pb-3 text-xs font-bold text-slate-400 uppercase tracking-wider text-right">
                          Receipt
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {recentInvoices.map((inv, idx) => (
                        <tr
                          key={idx}
                          className="hover:bg-white/50 transition-colors group"
                        >
                          <td className="py-4 text-sm font-medium text-slate-900">
                            {inv.date}
                          </td>
                          <td className="py-4 text-sm font-mono text-slate-500">
                            {inv.invoiceId}
                          </td>
                          <td className="py-4 text-sm font-bold text-slate-900">
                            {inv.amount}
                          </td>
                          <td className="py-4">
                            <span
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                                inv.status === "Paid"
                                  ? "bg-emerald-50 text-emerald-600 border border-emerald-100"
                                  : inv.status === "Pending"
                                    ? "bg-amber-50 text-amber-600 border border-amber-100"
                                    : "bg-red-50 text-red-600 border border-red-100"
                              }`}
                            >
                              {inv.status === "Paid" && (
                                <svg
                                  className="w-3 h-3"
                                  fill="none"
                                  viewBox="0 0 24 24"
                                  stroke="currentColor"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth="3"
                                    d="M5 13l4 4L19 7"
                                  />
                                </svg>
                              )}
                              {inv.status}
                            </span>
                          </td>
                          <td className="py-4 text-right">
                            <button className="text-slate-400 hover:text-[#FC6D26] transition-colors p-1">
                              <svg
                                className="w-5 h-5"
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

            {/* RIGHT COLUMN: API Details & Payment */}
            <div className="flex flex-col gap-6">
              {/* Dark Theme Gemini Breakdown */}
              <div className="bg-slate-950 rounded-[2rem] border border-slate-800 shadow-xl p-6 lg:p-8 relative overflow-hidden group">
                <div className="absolute inset-0 bg-gradient-to-br from-[#FC6D26]/10 to-transparent"></div>
                <div
                  className="absolute inset-0 opacity-10"
                  style={{
                    backgroundImage: `radial-gradient(circle at 1px 1px, white 1px, transparent 0)`,
                    backgroundSize: "16px 16px",
                  }}
                ></div>

                <div className="relative z-10 flex items-center gap-2 mb-6">
                  {/* AI Spark Icon */}
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
                    Gemini Cost Allocation
                  </h3>
                </div>

                <div className="relative z-10 space-y-6">
                  {geminiBreakdown.map((item, idx) => (
                    <div
                      key={idx}
                      className="border-b border-slate-800/80 pb-5 last:border-0 last:pb-0"
                    >
                      <div className="flex justify-between items-start mb-3">
                        <div>
                          <h4 className="text-sm font-bold text-slate-200">
                            {item.model}
                          </h4>
                          <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                            {item.percentage}% of total cost
                          </span>
                        </div>
                        <span className="text-base font-bold text-[#FC6D26]">
                          {item.cost}
                        </span>
                      </div>

                      <div className="space-y-2">
                        <div>
                          <div className="flex justify-between text-[10px] font-mono text-slate-400 mb-1">
                            <span>Input Tokens (Context)</span>
                            <span>{item.inputTokens}</span>
                          </div>
                          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
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
                          <div className="flex justify-between text-[10px] font-mono text-slate-400 mb-1">
                            <span>Output Tokens (Generated)</span>
                            <span>{item.outputTokens}</span>
                          </div>
                          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
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

                <div className="relative z-10 mt-6 pt-5 border-t border-slate-800 flex justify-between items-center text-xs">
                  <a
                    href="#"
                    className="text-slate-400 hover:text-white transition-colors underline decoration-slate-600 underline-offset-4"
                  >
                    Manage API Keys
                  </a>
                  <a
                    href="#"
                    className="text-[#FC6D26] hover:text-white transition-colors font-medium flex items-center gap-1"
                  >
                    View Pricing Docs
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
