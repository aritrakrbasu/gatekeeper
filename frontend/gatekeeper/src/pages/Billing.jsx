import React, { useState } from "react";

const Billing = () => {
  // Dummy data for Billing & Usage
  const billingCycle = "May 1 - May 31, 2026";

  const usageStats = {
    currentTotal: "$42.85",
    projectedTotal: "$58.00",
    totalTokens: "4.2M",
    mrsProcessed: 342,
  };

  const geminiBreakdown = [
    {
      model: "Gemini 1.5 Pro",
      inputTokens: "1.2M",
      outputTokens: "400K",
      cost: "$31.20",
      percentage: 75,
    },
    {
      model: "Gemini 1.5 Flash",
      inputTokens: "2.1M",
      outputTokens: "500K",
      cost: "$11.65",
      percentage: 25,
    },
  ];

  const recentInvoices = [
    {
      date: "May 1, 2026",
      amount: "$41.20",
      status: "Paid",
      invoiceId: "INV-2026-04",
    },
    {
      date: "Apr 1, 2026",
      amount: "$38.50",
      status: "Paid",
      invoiceId: "INV-2026-03",
    },
    {
      date: "Mar 1, 2026",
      amount: "$29.00",
      status: "Paid",
      invoiceId: "INV-2026-02",
    },
  ];

  // Simulated chart data for the last 14 days
  const chartData = [4, 7, 5, 12, 18, 15, 8, 5, 9, 22, 28, 14, 10, 16];
  const maxChartVal = Math.max(...chartData);

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
                12% vs last month
              </p>
            </div>

            <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm flex flex-col justify-between">
              <p className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-1">
                Gatekeeper Plan
              </p>
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-1 bg-slate-900 text-white text-xs font-bold rounded-lg uppercase tracking-wider">
                  Enterprise
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-2">
                Auto-renews June 1st
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
                  {chartData.map((val, idx) => (
                    <div
                      key={idx}
                      className="w-full relative group flex flex-col items-center justify-end h-full"
                    >
                      {/* Tooltip on hover */}
                      <div className="opacity-0 group-hover:opacity-100 absolute -top-8 bg-slate-900 text-white text-[10px] px-2 py-1 rounded transition-opacity whitespace-nowrap z-10 pointer-events-none">
                        {val * 100}k tokens
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
                  ))}
                </div>
                <div className="flex justify-between text-[10px] font-bold text-slate-400 mt-2 uppercase tracking-widest">
                  <span>May 14</span>
                  <span>May 21</span>
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
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-emerald-50 text-emerald-600 border border-emerald-100">
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
                              style={{ width: "80%" }}
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
                              style={{ width: "30%" }}
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

              {/* Payment Method Card */}
              <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 lg:p-8">
                <h3 className="text-lg font-bold text-slate-900 mb-5">
                  Payment Method
                </h3>

                <div className="p-4 rounded-xl border border-slate-200 bg-white flex items-center justify-between shadow-sm group">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-8 rounded bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0">
                      {/* Generic Credit Card SVG */}
                      <svg
                        className="w-6 h-6 text-slate-700"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth="1.5"
                          d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"
                        />
                      </svg>
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-slate-900 tracking-tight">
                        Visa ending in 4242
                      </h4>
                      <p className="text-xs text-slate-500">Expires 12/28</p>
                    </div>
                  </div>
                  <button className="text-sm font-medium text-slate-400 hover:text-slate-900 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100">
                    Edit
                  </button>
                </div>

                <button className="w-full mt-4 py-3 bg-slate-50 hover:bg-slate-100 text-slate-700 text-sm font-semibold rounded-xl transition-colors border border-slate-200 border-dashed">
                  + Add Payment Method
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>

    </div>
  );
};

export default Billing;
