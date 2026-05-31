import React, { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useRepositories, useConnectRepository } from "../services/queries";
import ConnectRepositoryModal from "../components/ConnectRepositoryModal";
import { formatLastSync } from "../utils/formatLastSync";

// Clean, high-class Structural Metric block for the dark telemetry card
const RepositoryMetricNode = ({ label, value, subtext, iconColor }) => {
  return (
    <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-3.5 flex items-center justify-between shadow-inner backdrop-blur-sm transition-all hover:bg-slate-900/50">
      <div>
        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-0.5">
          {label}
        </p>
        <div className="flex items-baseline gap-2">
          <h4 className="text-2xl font-semibold text-white tracking-tight leading-none">
            {value}
          </h4>
          {subtext && (
            <span className="text-[10px] font-medium text-slate-400">
              {subtext}
            </span>
          )}
        </div>
      </div>
      <div
        className={`w-2 h-2 rounded-full ${iconColor || "bg-slate-700"} shadow-[0_0_8px_currentColor]`}
      ></div>
    </div>
  );
};

const Repositories = () => {
  const [searchQuery, setSearchQuery] = useState("");
  const [showConnectModal, setShowConnectModal] = useState(false);

  // Use React Query hook for fetching repositories with caching
  const {
    data: repositories = [],
    isLoading,
    error,
    refetch,
  } = useRepositories();

  const connectMutation = useConnectRepository();

  const filteredRepositories = useMemo(() => {
    if (!searchQuery) {
      return repositories;
    }
    const query = searchQuery.toLowerCase();
    return repositories.filter(
      (repo) =>
        repo.name.toLowerCase().includes(query) ||
        repo.full_name?.toLowerCase().includes(query),
    );
  }, [searchQuery, repositories]);

  const handleConnectRepository = async (repo) => {
    try {
      await connectMutation.mutateAsync(repo.id);
    } catch (err) {
      console.error("Failed to connect repository:", err);
      throw err;
    }
  };

  const formatVisibility = (visibility) => {
    return (
      visibility?.charAt(0).toUpperCase() + visibility?.slice(1) || "Private"
    );
  };

  return (
    <div className="max-w-6xl mx-auto px-4 md:px-8">
      {/* Page Header & Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">
            Repositories
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage your connected projects and monitor Gatekeeper's AI review
            activity.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative">
            <svg
              className="w-5 h-5 text-slate-400 absolute left-3.5 top-1/2 transform -translate-y-1/2"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <input
              type="text"
              placeholder="Search repos..."
              className="pl-11 pr-4 py-2.5 bg-white/60 backdrop-blur-xl border border-white/80 rounded-2xl text-sm focus:outline-none focus:ring-2 focus:ring-[#FC6D26]/50 shadow-sm w-full md:w-64 placeholder-slate-400 text-slate-900 transition-all focus:bg-white"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <button
            onClick={() => setShowConnectModal(true)}
            className="bg-slate-900 hover:bg-slate-800 text-white font-medium py-2.5 px-5 rounded-2xl transition-all shadow-md flex items-center gap-2 text-sm shrink-0"
          >
            <svg
              className="w-4 h-4 text-[#FC6D26]"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M23.955 13.587l-1.342-4.135-2.664-8.189c-.135-.423-.73-.423-.867 0L16.418 9.45H7.582L4.919 1.263c-.137-.423-.733-.423-.868 0L1.387 9.452.045 13.587c-.121.374.016.786.335 1.018l11.62 8.442 11.62-8.442c.319-.232.456-.644.335-1.018z" />
            </svg>
            Import
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#FC6D26]"></div>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-6 mb-6">
          <div className="flex items-center gap-3">
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
                Error loading repositories
              </p>
              <p className="text-sm text-red-600">
                {error.message || "An error occurred"}
              </p>
            </div>
            <button
              onClick={() => refetch()}
              className="ml-auto px-4 py-2 bg-red-100 hover:bg-red-200 text-red-700 rounded-lg text-sm font-medium transition-colors"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {!isLoading && !error && filteredRepositories.length === 0 && (
        <div className="text-center py-20">
          <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg
              className="w-8 h-8 text-slate-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
              />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-slate-900 mb-2">
            No repositories found
          </h3>
          <p className="text-slate-500 mb-6">
            {searchQuery
              ? "Try a different search term"
              : "Import your first repository to get started"}
          </p>
          {!searchQuery && (
            <button
              onClick={() => setShowConnectModal(true)}
              className="bg-[#FC6D26] hover:bg-[#E24329] text-white font-medium py-2.5 px-5 rounded-2xl transition-all shadow-md"
            >
              Import Repository
            </button>
          )}
        </div>
      )}

      {!isLoading && !error && filteredRepositories.length > 0 && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {filteredRepositories.map((repo) => (
            <div
              key={repo.id}
              className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 hover:shadow-lg hover:shadow-slate-200/50 transition-all flex flex-col group"
            >
              {/* Repo Header */}
              <div className="flex items-start justify-between mb-6">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-2xl bg-white border border-slate-100 flex items-center justify-center shrink-0 shadow-sm group-hover:scale-105 transition-transform">
                    <svg
                      className="w-6 h-6 text-[#FC6D26]"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                    >
                      <path d="M23.955 13.587l-1.342-4.135-2.664-8.189c-.135-.423-.73-.423-.867 0L16.418 9.45H7.582L4.919 1.263c-.137-.423-.733-.423-.868 0L1.387 9.452.045 13.587c-.121.374.016.786.335 1.018l11.62 8.442 11.62-8.442c.319-.232.456-.644.335-1.018z" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                      {repo.name}
                      <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-500 text-[10px] font-bold uppercase tracking-wider border border-slate-200">
                        {formatVisibility(repo.visibility)}
                      </span>
                    </h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Last scan {formatLastSync(repo.last_sync)}
                    </p>
                  </div>
                </div>

                {/* Gatekeeper AI Status Indicator */}
                {repo.status === "active" || repo.status === "Healthy" ? (
                  <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wide bg-emerald-50 text-emerald-700 border border-emerald-100 shadow-sm">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                    Auto-Fix Enabled
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wide bg-blue-50 text-blue-700 border border-blue-100 shadow-sm">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
                    Review Only
                  </span>
                )}
              </div>

              {/* Specialized AI Metrics Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1">
                {/* MR Review Analytics (Light Theme) */}
                <div className="bg-slate-50/50 rounded-[1.25rem] p-5 border border-slate-100/80 flex flex-col justify-between hover:bg-slate-50 transition-colors">
                  <h4 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-5 flex items-center gap-1.5">
                    <svg
                      className="w-3.5 h-3.5 text-slate-500"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                      />
                    </svg>
                    Review Analytics
                  </h4>

                  <div className="space-y-4 flex-1 flex flex-col justify-center">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-slate-500 font-medium">
                        MRs Analyzed
                      </span>
                      <span className="text-sm font-bold text-slate-900">
                        {repo.metrics?.mrs_analyzed ?? repo.mrsAnalyzed ?? 0}
                      </span>
                    </div>

                    <div className="flex justify-between items-center">
                      <span className="text-sm text-slate-500 font-medium">
                        Avg. Review Time
                      </span>
                      <span className="text-sm font-bold text-emerald-600">
                        {repo.metrics?.avg_review_time ??
                          repo.avgReviewTime ??
                          "0s"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Auto-Remediation Engine (Dark Theme) */}
                <div className="bg-slate-900 rounded-[1.25rem] p-5 border border-slate-800 shadow-inner relative overflow-hidden flex flex-col justify-between gap-4">
                  {/* Fixed Dot Pattern matching Login Page */}
                  <div
                    className="absolute inset-0 opacity-20 pointer-events-none"
                    style={{
                      backgroundImage: `radial-gradient(circle at 1px 1px, white 1px, transparent 0)`,
                      backgroundSize: "24px 24px",
                    }}
                  ></div>
                  {/* Subtle Ambient Glow */}
                  <div className="absolute -right-10 -bottom-10 w-40 h-40 bg-[#FC6D26]/10 rounded-full blur-2xl pointer-events-none"></div>

                  <h4 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5 relative z-10">
                    <svg
                      className="w-3.5 h-3.5 text-[#FC6D26]"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2.5"
                        d="M13 10V3L4 14h7v7l9-11h-7z"
                      />
                    </svg>
                    Auto-Remediation
                  </h4>

                  <div className="grid grid-cols-1 gap-2.5 relative z-10 mt-1">
                    <RepositoryMetricNode
                      label="Auto-Fix MRs Opened"
                      value={
                        repo.metrics?.auto_fixes_proposed ??
                        repo.autoFixesProposed ??
                        0
                      }
                      iconColor="bg-[#FC6D26] text-[#FC6D26]"
                    />
                    <RepositoryMetricNode
                      label="Fixes Merged"
                      value={
                        repo.metrics?.fixes_merged ?? repo.fixesMerged ?? 0
                      }
                      subtext="Successfully applied"
                      iconColor="bg-emerald-400 text-emerald-400"
                    />
                  </div>
                </div>
              </div>

              {/* Card Footer Actions */}
              <div className="mt-6 pt-5 border-t border-slate-100 flex items-center justify-between">
                <button className="text-sm font-medium text-slate-500 hover:text-slate-900 transition-colors flex items-center gap-1.5">
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
                      d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                    />
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                    />
                  </svg>
                  Settings
                </button>
                <Link
                  to={`/repositories/${repo.id}`}
                  className="text-sm font-semibold text-[#FC6D26] hover:text-[#E24329] transition-colors flex items-center gap-1.5 bg-[#FC6D26]/10 px-3 py-1.5 rounded-lg"
                >
                  View Gatekeeper Activity
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
                      d="M9 5l7 7-7 7"
                    />
                  </svg>
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Connect Repository Modal */}
      <ConnectRepositoryModal
        isOpen={showConnectModal}
        onClose={() => setShowConnectModal(false)}
        onConnect={handleConnectRepository}
      />
    </div>
  );
};

export default Repositories;
