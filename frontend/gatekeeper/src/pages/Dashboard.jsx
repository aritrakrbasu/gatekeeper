import React, { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useRecentMRs, useRepositories, useConnectRepository } from "../services/queries";
import ConnectRepositoryModal from "../components/ConnectRepositoryModal";

const Dashboard = () => {
  const navigate = useNavigate();
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [user, setUser] = useState(null);

  // Get user from localStorage
  useState(() => {
    const userData = localStorage.getItem("user");
    if (userData) {
      setUser(JSON.parse(userData));
    }
  });

  // Use React Query hooks with automatic caching and refetching
  const { data: recentMRs = [] } = useRecentMRs(10);
  const { data: repositories = [] } = useRepositories({ limit: 5 });

  // Use React Query mutation for connecting repositories
  const connectMutation = useConnectRepository();

  // Transform repositories data for display
  const repos = useMemo(() => {
    return repositories.map(repo => ({
      name: repo.name,
      health: `${repo.health_score || 0}%`
    }));
  }, [repositories]);

  // Dummy data for the new sparkline chart
  const reviewTimeTrend = [65, 55, 75, 45, 50, 40, 45]; // Heights in percentage
  const maxTrend = Math.max(...reviewTimeTrend);

  return (
    <div className="max-w-6xl mx-auto px-4 md:px-8">
      {/* Desktop Notification Area */}
      <div className="hidden md:flex justify-end mb-6">
        <button className="relative w-12 h-12 rounded-full bg-white/60 backdrop-blur-xl border border-white/80 flex items-center justify-center text-slate-400 hover:text-slate-900 shadow-[0_8px_32px_rgba(0,0,0,0.04)] transition-all hover:scale-105">
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
              d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
            />
          </svg>
          <span className="absolute top-3 right-3 w-2.5 h-2.5 bg-[#FC6D26] rounded-full border-2 border-white"></span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 auto-rows-[minmax(180px,auto)]">
        {/* Card 1: Welcome Hero */}
        <div className="col-span-1 md:col-span-4 lg:col-span-2 bg-gradient-to-br from-[#FC6D26]/10 to-[#FC6D26]/5 rounded-[2rem] border border-[#FC6D26]/10 p-8 flex flex-col justify-between relative overflow-hidden shadow-sm hover:shadow-md transition-shadow backdrop-blur-sm">
          <div className="absolute -right-10 -top-10 w-40 h-40 bg-[#FC6D26]/20 rounded-full blur-3xl"></div>
          <div className="z-10">
            <h2 className="text-3xl font-semibold text-slate-900 tracking-tight mb-2">
              Morning, {user?.name || "John"}.
            </h2>
            <p className="text-slate-600 text-sm max-w-sm leading-relaxed">
              Gatekeeper has reviewed 14 merge requests while you were away.
              Everything is running smoothly.
            </p>
          </div>
          <div className="mt-8 z-10">
            <button
              onClick={() => setShowConnectModal(true)}
              className="bg-slate-900 hover:bg-slate-800 text-white font-medium py-3 px-6 rounded-2xl transition-all shadow-md flex items-center gap-2 text-sm w-max hover:-translate-y-0.5"
            >
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
                  d="M12 4v16m8-8H4"
                />
              </svg>
              Connect New Repository
            </button>
          </div>
        </div>

        {/* Card 2: Classy Micro-Stat (Avg Review Time) */}
        <div className="col-span-1 md:col-span-2 lg:col-span-1 bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 lg:p-8 flex flex-col justify-between hover:shadow-md transition-shadow relative overflow-hidden group">
          <div className="flex justify-between items-start z-10 mb-4">
            <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">
              Avg Review Time
            </h3>
            <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded-full border border-emerald-100 shadow-sm">
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
              12%
            </span>
          </div>

          <div className="z-10 flex-1">
            <div className="flex items-baseline gap-1">
              <h2 className="text-6xl font-bold text-slate-900 tracking-tighter">
                45
              </h2>
              <span className="text-2xl font-medium text-slate-400">s</span>
            </div>
            <p className="text-xs text-slate-500 mt-2 font-medium">
              Across all repositories
            </p>
          </div>

          {/* Elegant SVG Sparkline Curve */}
          <div className="absolute bottom-0 left-0 right-0 h-24 pointer-events-none opacity-40 group-hover:opacity-70 transition-opacity duration-500">
            <svg
              viewBox="0 0 100 40"
              preserveAspectRatio="none"
              className="w-full h-full text-[#FC6D26]"
            >
              <path
                d="M0,40 L0,25 C15,20 25,35 40,25 C55,15 70,35 85,15 L100,20 L100,40 Z"
                fill="currentColor"
                opacity="0.1"
              />
              <path
                d="M0,25 C15,20 25,35 40,25 C55,15 70,35 85,15 L100,20"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              />
            </svg>
          </div>
        </div>

        {/* Card 3: Classy Micro-Stat (Issues Prevented) */}
        <div className="col-span-1 md:col-span-2 lg:col-span-1 bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 lg:p-8 flex flex-col hover:shadow-md transition-shadow relative overflow-hidden">
          <div className="flex justify-between items-start mb-6">
            <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">
              Issues Prevented
            </h3>
            <div className="w-8 h-8 rounded-full bg-slate-50 border border-slate-100 flex items-center justify-center shadow-sm">
              <svg
                className="w-4 h-4 text-slate-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
            </div>
          </div>

          <div className="mb-6">
            <h2 className="text-6xl font-bold text-slate-900 tracking-tighter leading-none">
              342
            </h2>
          </div>

          {/* Minimal Dot-Grid Breakdown */}
          <div className="space-y-3 flex-1 flex flex-col justify-end">
            <div className="flex items-center gap-3">
              <div className="w-1.5 h-1.5 rounded-full bg-rose-500"></div>
              <span className="text-xs font-medium text-slate-600 flex-1">
                Security Vectors
              </span>
              <span className="text-xs font-bold text-slate-900">145</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-1.5 h-1.5 rounded-full bg-amber-400"></div>
              <span className="text-xs font-medium text-slate-600 flex-1">
                Logic Errors
              </span>
              <span className="text-xs font-bold text-slate-900">112</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-1.5 h-1.5 rounded-full bg-slate-300"></div>
              <span className="text-xs font-medium text-slate-600 flex-1">
                Performance
              </span>
              <span className="text-xs font-bold text-slate-900">85</span>
            </div>
          </div>
        </div>

        {/* Card 4: MR Queue */}
        <div className="col-span-1 md:col-span-4 lg:col-span-2 row-span-2 bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-8 flex flex-col hover:shadow-md transition-shadow">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-lg font-semibold text-slate-900">
              Active Queue
            </h3>
            <button className="text-sm text-[#FC6D26] font-medium hover:text-[#E24329]">
              View all
            </button>
          </div>
          <div className="flex-1">
            {recentMRs.length === 0 ? (
              // No data state
              <div className="flex-1 flex flex-col items-center justify-center text-center py-8">
                <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mb-4">
                  <svg className="w-8 h-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <p className="text-sm font-medium text-slate-900 mb-1">No merge requests found</p>
                <p className="text-xs text-slate-500">Recent MRs will appear here once available</p>
              </div>
            ) : (
              // MRs list
              <div className="space-y-3">
                {recentMRs.map((mr, i) => (
                  <div
                    key={i}
                    className="group p-4 rounded-2xl border border-white/60 bg-white/40 hover:bg-white/80 transition-all flex items-center justify-between cursor-pointer shadow-sm"
                  >
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-xl bg-white border border-slate-100 flex items-center justify-center shadow-sm">
                        <svg
                          className="w-5 h-5 text-slate-400 group-hover:text-[#FC6D26] transition-colors"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2"
                            d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2"
                          />
                        </svg>
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-slate-900 mb-0.5">
                          {mr.title}
                        </p>
                        <p className="text-xs text-slate-500">
                          {mr.id} • {mr.repo}
                        </p>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      {mr.status === "Reviewing" && (
                        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide bg-blue-100/80 text-blue-700">
                          <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-ping"></span>{" "}
                          Reviewing
                        </span>
                      )}
                      {mr.status === "Approved" && (
                        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide bg-emerald-100/80 text-emerald-700">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>{" "}
                          Approved
                        </span>
                      )}
                      {mr.status === "Issues" && (
                        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide bg-rose-100/80 text-rose-700">
                          <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>{" "}
                          Issues
                        </span>
                      )}
                      <span className="text-[11px] text-slate-400 font-medium">
                        {mr.time}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Card 5: Dark Health Gauge (Enhanced with Dot Matrix) */}
        <div className="col-span-1 md:col-span-2 lg:col-span-1 row-span-2 bg-slate-900 rounded-[2rem] border border-slate-800 shadow-xl p-8 flex flex-col items-center justify-center relative overflow-hidden text-center">
          {/* Subtle gradient glow */}
          <div className="absolute inset-0 bg-gradient-to-t from-emerald-500/10 to-transparent z-0"></div>

          {/* Technical Dot Matrix Pattern */}
          <div
            className="absolute inset-0 opacity-20 z-0 pointer-events-none"
            style={{
              backgroundImage: `radial-gradient(circle at 1px 1px, white 1px, transparent 0)`,
              backgroundSize: "24px 24px",
            }}
          ></div>

          <h3 className="text-white font-medium text-sm mb-6 z-10">
            Global Code Health
          </h3>
          <div className="relative w-32 h-32 mb-6 z-10">
            <svg
              className="w-full h-full transform -rotate-90"
              viewBox="0 0 100 100"
            >
              <circle
                cx="50"
                cy="50"
                r="40"
                stroke="currentColor"
                strokeWidth="8"
                fill="transparent"
                className="text-slate-800"
              />
              <circle
                cx="50"
                cy="50"
                r="40"
                stroke="currentColor"
                strokeWidth="8"
                fill="transparent"
                strokeDasharray="251.2"
                strokeDashoffset="30.14"
                className="text-emerald-400 drop-shadow-[0_0_10px_rgba(52,211,153,0.5)] transition-all duration-1000 ease-out"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-bold text-white tracking-tight">
                88<span className="text-lg text-emerald-400">%</span>
              </span>
            </div>
          </div>
          <p className="text-slate-400 text-xs z-10 max-w-[140px]">
            Based on automated static analysis and MR approvals.
          </p>
        </div>

        {/* Card 6: Connected Repositories */}
        <div className="col-span-1 md:col-span-2 lg:col-span-1 row-span-2 bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-8 flex flex-col hover:shadow-md transition-shadow">
          <h3 className="text-lg font-semibold text-slate-900 mb-6">
            Connected Repos
          </h3>
          <div className="flex-1 flex flex-col">
            {repos.length === 0 ? (
              // No data state
              <div className="flex-1 flex flex-col items-center justify-center text-center py-8">
                <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mb-4">
                  <svg className="w-8 h-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                  </svg>
                </div>
                <p className="text-sm font-medium text-slate-900 mb-1">No repositories found</p>
                <p className="text-xs text-slate-500 mb-4">Connect your first repository to get started</p>
                <button
                  onClick={() => setShowConnectModal(true)}
                  className="px-4 py-2 bg-[#FC6D26] hover:bg-[#E24329] text-white text-sm font-medium rounded-xl transition-all"
                >
                  Connect Repository
                </button>
              </div>
            ) : (
              // Repos list
              <>
                <div className="flex flex-col gap-4">
                  {repos.map((repo, i) => (
                    <div key={i} className="flex items-center gap-4">
                      <div className="w-12 h-12 rounded-2xl bg-white border border-slate-100 flex items-center justify-center shrink-0 shadow-sm">
                        <svg
                          className="w-6 h-6 text-[#FC6D26]"
                          viewBox="0 0 24 24"
                          fill="currentColor"
                        >
                          <path d="M23.955 13.587l-1.342-4.135-2.664-8.189c-.135-.423-.73-.423-.867 0L16.418 9.45H7.582L4.919 1.263c-.137-.423-.733-.423-.868 0L1.387 9.452.045 13.587c-.121.374.016.786.335 1.018l11.62 8.442 11.62-8.442c.319-.232.456-.644.335-1.018z" />
                        </svg>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-slate-900 truncate">
                          {repo.name}
                        </p>
                        <div className="w-full bg-slate-200/50 h-1.5 rounded-full mt-2 overflow-hidden">
                          <div
                            className="bg-slate-900 h-1.5 rounded-full"
                            style={{ width: repo.health }}
                          ></div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <button className="mt-auto w-full py-3 rounded-2xl border-2 border-dashed border-slate-300 text-slate-500 font-medium text-sm hover:border-[#FC6D26] hover:text-[#FC6D26] hover:bg-white transition-all">
                  + View all {repos.length} repos
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Connect Repository Modal */}
      <ConnectRepositoryModal
        isOpen={showConnectModal}
        onClose={() => setShowConnectModal(false)}
        onConnect={async (repo, selectedBranches) => {
          try {
            await connectMutation.mutateAsync({
              repoId: repo.id,
              targetBranches: selectedBranches || ["main", "master", "develop"]
            });
            console.log("Connected repository:", repo);
          } catch (err) {
            console.error("Failed to connect repository:", err);
          }
        }}
      />
    </div>
  );
};

export default Dashboard;
