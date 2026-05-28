import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import {
  useRepository,
  useRepositoryMRs,
  useRepositoryPolicies,
  useSubmitFeedback,
} from "../services/queries";

const RepoDetails = () => {
  const { id } = useParams();
  const [selectedMR, setSelectedMR] = useState(null);
  const [feedback, setFeedback] = useState({
    vote: null,
    text: "",
    submitted: false,
  });

  // Fetch repository details
  const {
    data: repo,
    isLoading: repoLoading,
    error: repoError,
  } = useRepository(id);

  // Fetch merge requests (no auto-refresh - uses manual sync button)
  const {
    data: repoMRs = [],
    isLoading: mrsLoading,
    refetch,
    isFetching,
  } = useRepositoryMRs(id);

  // Fetch policies
  const { data: activePolicies = [] } = useRepositoryPolicies(id);

  // Feedback mutation
  const feedbackMutation = useSubmitFeedback();

  // Loading state
  if (repoLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#FC6D26]"></div>
      </div>
    );
  }

  // Error state
  if (repoError) {
    return (
      <div className="max-w-6xl mx-auto px-4 md:px-8 py-8">
        <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6">
          <p className="text-rose-800">
            Failed to load repository: {repoError.message}
          </p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-rose-600 text-white rounded-lg hover:bg-rose-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Default values if repo not loaded yet
  const repoData = repo || {
    name: "Loading...",
    visibility: "Unknown",
    lastSync: "Unknown",
    healthScore: 0,
    stats: {
      mrsReviewed: 0,
      avg_review_time: "0s",
      auto_fixes_applied: 0,
      testCoverage: "0%",
    },
    vectorAnalysis: {
      security: "0%",
      performance: "0%",
      complexity: "0%",
    },
  };

  // Map backend stats to frontend format
  const stats = {
    mrsReviewed: repoData.stats?.mrs_reviewed || repoMRs.length,
    avgTime: repoData.stats?.avg_review_time || "0s",
    autoFixes: repoData.stats?.auto_fixes_applied || 0,
    testCoverage: repoData.stats?.test_coverage || "0%",
  };

  const repoMRsList = repoMRs || [];

  // Map policies to expected format
  const policiesList = activePolicies.map((policy) => ({
    name: policy.name || policy,
    active:
      policy.enabled !== undefined
        ? policy.enabled
        : policy.active !== undefined
          ? policy.active
          : true,
  }));

  const closeModal = () => {
    setSelectedMR(null);
    setFeedback({ vote: null, text: "", submitted: false });
  };

  const handleVote = (voteType) => {
    if (feedback.submitted) return;
    setFeedback({ ...feedback, vote: voteType });
  };

  const submitFeedback = async () => {
    try {
      await feedbackMutation.mutateAsync({
        repoId: id,
        mrId: selectedMR.gitlab_mr_id || selectedMR.id,
        vote: feedback.vote,
        comment: feedback.text,
      });
      setFeedback({ ...feedback, submitted: true });
    } catch (err) {
      console.error("Failed to submit feedback:", err);
    }
  };

  const handleSync = () => {
    refetch();
  };

  return (
    <div className="max-w-6xl mx-auto px-4 md:px-8">
      {/* Breadcrumb & Header */}
      <div className="mb-8">
        <div className="flex items-center gap-2 text-sm text-slate-500 mb-4 font-medium">
          <Link
            to="/repositories"
            className="hover:text-slate-900 transition-colors"
          >
            Repositories
          </Link>
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
          <span className="text-slate-900 bg-white/60 px-2.5 py-1 rounded-lg border border-white/80">
            {repoData.name || "Unknown"}
          </span>
        </div>

        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-[1.25rem] bg-white border border-slate-100 flex items-center justify-center shrink-0 shadow-sm">
              <svg
                className="w-8 h-8 text-[#FC6D26]"
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <path d="M23.955 13.587l-1.342-4.135-2.664-8.189c-.135-.423-.73-.423-.867 0L16.418 9.45H7.582L4.919 1.263c-.137-.423-.733-.423-.868 0L1.387 9.452.045 13.587c-.121.374.016.786.335 1.018l11.62 8.442 11.62-8.442c.319-.232.456-.644.335-1.018z" />
              </svg>
            </div>
            <div>
              <h1 className="text-3xl font-bold text-slate-900 tracking-tight flex items-center gap-3">
                {repoData.name || "Unknown Repository"}
                <span className="px-2.5 py-1 rounded-md bg-slate-200/50 text-slate-600 text-[10px] font-bold uppercase tracking-wider border border-slate-200">
                  {repoData.visibility || "Private"}
                </span>
              </h1>
              <p className="text-sm text-slate-500 mt-1 flex items-center gap-2">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-emerald-500"></span>{" "}
                  Online
                </span>
                • Last synced {repoData.lastSync || "Unknown"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleSync}
              disabled={isFetching}
              className="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <svg
                className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              {isFetching ? "Syncing..." : "Sync"}
            </button>
            <a
              href={repoData.url || "#"}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-slate-900 hover:bg-slate-800 text-white font-medium py-2.5 px-4 rounded-2xl transition-all shadow-md flex items-center gap-2 text-sm"
            >
              View on GitLab
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
                  d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                />
              </svg>
            </a>
          </div>
        </div>
      </div>

      {/* Core Metrics Ribbon */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm">
          <p className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-1">
            MRs Reviewed
          </p>
          <p className="text-2xl font-bold text-slate-900">
            {stats.mrsReviewed}
          </p>
        </div>
        <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm">
          <p className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-1">
            Avg Review Time
          </p>
          <p className="text-2xl font-bold text-slate-900">{stats.avgTime}</p>
        </div>
        <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm relative overflow-hidden">
          <p className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-1 relative z-10">
            Auto-Fixes Proposed
          </p>
          <p className="text-2xl font-bold text-[#FC6D26] relative z-10">
            {stats.autoFixes}
          </p>
          {/* Subtle ambient glow for the key metric */}
          <div className="absolute right-[-20%] bottom-[-50%] w-24 h-24 bg-[#FC6D26]/10 rounded-full blur-xl pointer-events-none"></div>
        </div>
        <div className="bg-white/70 backdrop-blur-xl rounded-[1.5rem] border border-white/80 p-5 shadow-sm">
          <p className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-1">
            Test Coverage
          </p>
          <p className="text-2xl font-bold text-emerald-600">
            {stats.testCoverage}
          </p>
        </div>
      </div>

      {/* Main Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* LEFT COLUMN: MR Feed */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 lg:p-8">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-bold text-slate-900">
                Merge Requests Feed
              </h3>
              <div className="flex items-center gap-2">
                {mrsLoading && (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-[#FC6D26]"></div>
                )}
                <button className="text-sm font-semibold text-[#FC6D26] bg-[#FC6D26]/10 px-3 py-1.5 rounded-lg hover:bg-[#FC6D26]/20 transition-colors">
                  Filter
                </button>
              </div>
            </div>

            <div className="space-y-3">
              {repoMRsList.length === 0 ? (
                <div className="text-center py-12">
                  <p className="text-slate-500">
                    No merge requests found. Sync to fetch latest data.
                  </p>
                </div>
              ) : (
                repoMRsList.map((mr, i) => {
                  // Map backend status to frontend display
                  const getStatusDisplay = (status) => {
                    switch (status) {
                      case "open":
                        return "Reviewing";
                      case "merged":
                        return "Approved";
                      case "closed":
                        return "Closed";
                      case "draft":
                        return "Draft";
                      default:
                        return "Reviewing";
                    }
                  };

                  const statusDisplay = getStatusDisplay(mr.status);

                  return (
                    <div
                      key={i}
                      onClick={() => setSelectedMR(mr)}
                      className={`group p-4 rounded-[1.25rem] bg-white/50 hover:bg-white transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4 cursor-pointer shadow-sm hover:shadow-md hover:-translate-y-0.5 ${mr.isAutoFix ? "border-[1.5px] border-[#FC6D26]/40 bg-gradient-to-r from-[#FC6D26]/5 to-transparent" : "border border-white/60"}`}
                    >
                      <div className="flex items-start sm:items-center gap-4">
                        {mr.isAutoFix ? (
                          <div className="w-10 h-10 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center shrink-0 relative shadow-sm">
                            <div className="absolute inset-0 bg-[#FC6D26] blur opacity-20 rounded-xl"></div>
                            {/* AI Spark Icon */}
                            <svg
                              className="w-5 h-5 text-[#FC6D26] relative z-10"
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
                          </div>
                        ) : (
                          <div className="w-10 h-10 rounded-xl bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0">
                            <svg
                              className="w-5 h-5 text-slate-500 group-hover:text-slate-900 transition-colors"
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
                        )}

                        <div>
                          <p className="text-sm font-bold text-slate-900 mb-1 flex items-center gap-2">
                            {mr.title}
                            {mr.isAutoFix && (
                              <span className="px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest bg-[#FC6D26]/10 text-[#FC6D26] rounded-md border border-[#FC6D26]/20">
                                Auto-Fix
                              </span>
                            )}
                          </p>
                          <div className="flex items-center gap-2 text-xs font-mono text-slate-500">
                            <span className="bg-slate-200/50 px-1.5 py-0.5 rounded text-slate-600">
                              {mr.branch}
                            </span>
                            <svg
                              className="w-3 h-3 text-slate-400"
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth="2"
                                d="M14 5l7 7m0 0l-7 7m7-7H3"
                              />
                            </svg>
                            <span className="bg-slate-200/50 px-1.5 py-0.5 rounded text-slate-600">
                              {mr.target}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="flex flex-row sm:flex-col items-center sm:items-end justify-between sm:justify-center gap-2 sm:gap-1.5 ml-14 sm:ml-0">
                        {statusDisplay === "Reviewing" && (
                          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide bg-blue-100/80 text-blue-700 border border-blue-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-ping"></span>{" "}
                            Reviewing
                          </span>
                        )}
                        {statusDisplay === "Approved" && (
                          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide bg-emerald-100/80 text-emerald-700 border border-emerald-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>{" "}
                            Approved
                          </span>
                        )}
                        {statusDisplay === "Closed" && (
                          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide bg-slate-100/80 text-slate-700 border border-slate-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-slate-500"></span>{" "}
                            Closed
                          </span>
                        )}
                        {statusDisplay === "Draft" && (
                          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide bg-slate-100/80 text-slate-700 border border-slate-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-slate-500"></span>{" "}
                            Draft
                          </span>
                        )}
                        <span className="text-[11px] text-slate-400 font-medium whitespace-nowrap">
                          {mr.isAutoFix ? (
                            <span className="text-[#FC6D26] font-semibold">
                              {mr.author}
                            </span>
                          ) : (
                            mr.id
                          )}{" "}
                          • {mr.time}
                        </span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Vector Engine & Policies */}
        <div className="flex flex-col gap-6">
          {/* AI Core Analysis Terminal Card */}
          <div className="bg-slate-900 rounded-[2rem] border border-slate-800 shadow-xl p-6 lg:p-8 relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-[#FC6D26]/10 to-transparent"></div>
            <div
              className="absolute inset-0 opacity-10"
              style={{
                backgroundImage: `radial-gradient(circle at 1px 1px, white 1px, transparent 0)`,
                backgroundSize: "16px 16px",
              }}
            ></div>

            <div className="relative z-10 flex items-center gap-2 mb-6">
              <div className="w-2 h-2 rounded-full bg-[#FC6D26] animate-pulse"></div>
              <h3 className="text-white font-bold text-sm tracking-widest uppercase">
                AI Insight Engine
              </h3>
            </div>

            <div className="relative z-10 mb-6 flex justify-center">
              <div className="relative w-32 h-32">
                <svg
                  className="w-full h-full transform -rotate-90"
                  viewBox="0 0 100 100"
                >
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    stroke="currentColor"
                    strokeWidth="6"
                    fill="transparent"
                    className="text-slate-800"
                  />
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    stroke="currentColor"
                    strokeWidth="6"
                    fill="transparent"
                    strokeDasharray="251.2"
                    strokeDashoffset="5.024"
                    className="text-emerald-400 drop-shadow-[0_0_8px_rgba(52,211,153,0.6)]"
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-3xl font-bold text-white tracking-tight">
                    {repoData.healthScore || 0}
                    <span className="text-base text-emerald-400 ml-1">
                      /100
                    </span>
                  </span>
                </div>
              </div>
            </div>

            {/* Vector Analysis Subsections */}
            <div className="relative z-10 space-y-4 pt-2 border-t border-slate-800">
              <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                Vector Analysis
              </h4>
              <div>
                <div className="flex justify-between items-center text-xs font-mono mb-1">
                  <span className="text-slate-400">Security Vector</span>
                  <span className="text-emerald-400">
                    Optimal ({repoData.vectorAnalysis?.security || "0%"})
                  </span>
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                  <div className="bg-emerald-500 w-[90%] h-full rounded-full"></div>
                </div>
              </div>
              <div>
                <div className="flex justify-between items-center text-xs font-mono mb-1">
                  <span className="text-slate-400">Performance Index</span>
                  <span className="text-emerald-400">
                    Stable ({repoData.vectorAnalysis?.performance || "0%"})
                  </span>
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                  <div className="bg-emerald-500 w-[85%] h-full rounded-full"></div>
                </div>
              </div>
              <div>
                <div className="flex justify-between items-center text-xs font-mono mb-1">
                  <span className="text-slate-400">Complexity Weight</span>
                  <span className="text-emerald-400">
                    Reduced ({repoData.vectorAnalysis?.complexity || "0%"})
                  </span>
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                  <div className="bg-emerald-400 w-[30%] h-full rounded-full"></div>
                </div>
              </div>
            </div>
          </div>

          {/* Connected Active Review Policies List */}
          <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 lg:p-8">
            <div className="flex justify-between items-center mb-5">
              <h3 className="text-lg font-bold text-slate-900">
                Active Policies
              </h3>
              <button className="text-slate-400 hover:text-slate-900 transition-colors">
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
                    d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                  />
                </svg>
              </button>
            </div>
            <div className="space-y-3">
              {policiesList.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-slate-500 text-sm">
                    No policies configured
                  </p>
                </div>
              ) : (
                policiesList.map((policy, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <div
                      className={`mt-0.5 shrink-0 w-5 h-5 rounded flex items-center justify-center ${policy.active ? "bg-emerald-100 text-emerald-600" : "bg-slate-100 text-slate-300"}`}
                    >
                      {policy.active ? (
                        <svg
                          className="w-3.5 h-3.5"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2.5"
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                      ) : (
                        <svg
                          className="w-3.5 h-3.5"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2"
                            d="M18 12H6"
                          />
                        </svg>
                      )}
                    </div>
                    <span
                      className={`text-sm ${policy.active ? "text-slate-700 font-medium" : "text-slate-400 line-through"}`}
                    >
                      {policy.name}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* =========================================
          MR DETAILS POPUP / MODAL OVERLAY
          ========================================= */}
      {selectedMR && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6">
          <div
            className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity"
            onClick={closeModal}
          ></div>

          <div className="relative w-full max-w-3xl bg-white/95 backdrop-blur-2xl border border-white rounded-[2rem] shadow-2xl overflow-hidden flex flex-col max-h-[90vh] animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-white/50">
              <div className="flex items-center gap-3">
                {selectedMR.isAutoFix ? (
                  <div className="w-10 h-10 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center shrink-0">
                    <svg
                      className="w-5 h-5 text-[#FC6D26]"
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
                  </div>
                ) : (
                  <div className="w-10 h-10 rounded-xl bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0">
                    <svg
                      className="w-5 h-5 text-slate-500"
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
                )}
                <div>
                  <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                    {selectedMR.title}
                    {selectedMR.isAutoFix && (
                      <span className="px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest bg-[#FC6D26]/10 text-[#FC6D26] rounded-md border border-[#FC6D26]/20">
                        Auto-Fix
                      </span>
                    )}
                  </h2>
                  <p className="text-sm text-slate-500">
                    {selectedMR.isAutoFix ? "Generated by" : "Opened by"}{" "}
                    <span
                      className={`font-medium ${selectedMR.isAutoFix ? "text-[#FC6D26]" : "text-slate-700"}`}
                    >
                      {selectedMR.author}
                    </span>{" "}
                    • {selectedMR.time}
                  </p>
                </div>
              </div>
              <button
                onClick={closeModal}
                className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 hover:bg-slate-200 hover:text-slate-900 transition-colors"
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
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Branch Details */}
              <div className="flex flex-wrap gap-4 items-center justify-between bg-slate-50/80 p-4 rounded-2xl border border-slate-100">
                <div className="flex items-center gap-2 text-sm font-mono text-slate-600">
                  <span className="bg-white px-2 py-1 rounded border border-slate-200 shadow-sm">
                    {selectedMR.branch}
                  </span>
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
                      d="M14 5l7 7m0 0l-7 7m7-7H3"
                    />
                  </svg>
                  <span className="bg-white px-2 py-1 rounded border border-slate-200 shadow-sm">
                    {selectedMR.target}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-sm font-medium">
                  <span className="flex items-center gap-1 text-emerald-600">
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
                        d="M12 6v6m0 0v6m0-6h6m-6 0H6"
                      />
                    </svg>
                    {selectedMR.changes.added}
                  </span>
                  <span className="flex items-center gap-1 text-rose-600">
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
                        d="M18 12H6"
                      />
                    </svg>
                    {selectedMR.changes.removed}
                  </span>
                  <span className="text-slate-500 px-2 border-l border-slate-300">
                    {selectedMR.changes.files} files changed
                  </span>
                </div>
              </div>

              {/* Gatekeeper AI Inside-Modal Analysis Feedback */}
              <div
                className={`rounded-2xl overflow-hidden shadow-xl flex flex-col ${selectedMR.isAutoFix ? "bg-slate-950 border border-[#FC6D26]/30" : "bg-slate-900 border border-slate-800"}`}
              >
                <div
                  className={`px-4 py-3 border-b flex items-center gap-2 ${selectedMR.isAutoFix ? "bg-[#FC6D26]/10 border-[#FC6D26]/20" : "bg-slate-800/50 border-slate-700/50"}`}
                >
                  <div
                    className={`w-2 h-2 rounded-full animate-pulse ${selectedMR.isAutoFix ? "bg-[#FC6D26]" : "bg-emerald-400"}`}
                  ></div>
                  <span
                    className={`text-xs font-bold uppercase tracking-wider ${selectedMR.isAutoFix ? "text-[#FC6D26]" : "text-slate-300"}`}
                  >
                    {selectedMR.isAutoFix
                      ? "Gatekeeper Auto-Fix Generation Summary"
                      : "Gatekeeper AI Review Summary"}
                  </span>
                </div>

                <div className="p-5 flex-1 relative overflow-hidden">
                  {selectedMR.isAutoFix && (
                    <div className="absolute right-[-10%] top-[-10%] w-32 h-32 bg-[#FC6D26]/10 rounded-full blur-2xl pointer-events-none"></div>
                  )}
                  <div className="text-slate-300 text-sm leading-relaxed relative z-10 prose prose-invert prose-sm max-w-none">
                    <ReactMarkdown
                      components={{
                        h1: ({ node, ...props }) => (
                          <h1
                            className="text-lg font-bold text-white mb-3"
                            {...props}
                          />
                        ),
                        h2: ({ node, ...props }) => (
                          <h2
                            className="text-base font-bold text-white mb-2 mt-4"
                            {...props}
                          />
                        ),
                        h3: ({ node, ...props }) => (
                          <h3
                            className="text-sm font-bold text-white mb-2 mt-3"
                            {...props}
                          />
                        ),
                        p: ({ node, ...props }) => (
                          <p className="mb-2 text-slate-300" {...props} />
                        ),
                        ul: ({ node, ...props }) => (
                          <ul
                            className="list-disc list-inside mb-3 text-slate-300"
                            {...props}
                          />
                        ),
                        ol: ({ node, ...props }) => (
                          <ol
                            className="list-decimal list-inside mb-3 text-slate-300"
                            {...props}
                          />
                        ),
                        li: ({ node, ...props }) => (
                          <li className="mb-1" {...props} />
                        ),
                        code: ({ node, inline, ...props }) =>
                          inline ? (
                            <code
                              className="bg-slate-800 px-1 py-0.5 rounded text-emerald-400 text-xs"
                              {...props}
                            />
                          ) : (
                            <code
                              className="block bg-slate-800 p-2 rounded text-emerald-400 text-xs my-2 overflow-x-auto"
                              {...props}
                            />
                          ),
                        pre: ({ node, ...props }) => (
                          <pre
                            className="bg-slate-900 p-3 rounded-lg overflow-x-auto my-3"
                            {...props}
                          />
                        ),
                        strong: ({ node, ...props }) => (
                          <strong className="font-bold text-white" {...props} />
                        ),
                        blockquote: ({ node, ...props }) => (
                          <blockquote
                            className="border-l-4 border-slate-600 pl-4 italic text-slate-400 my-3"
                            {...props}
                          />
                        ),
                        a: ({ node, ...props }) => (
                          <a
                            className="text-[#FC6D26] hover:text-[#FC6D26]/80 underline"
                            {...props}
                          />
                        ),
                        table: ({ node, ...props }) => (
                          <div className="overflow-x-auto my-3">
                            <table
                              className="min-w-full divide-y divide-slate-700"
                              {...props}
                            />
                          </div>
                        ),
                        th: ({ node, ...props }) => (
                          <th
                            className="px-3 py-2 text-left text-xs font-medium text-slate-300 uppercase tracking-wider"
                            {...props}
                          />
                        ),
                        td: ({ node, ...props }) => (
                          <td
                            className="px-3 py-2 text-sm text-slate-400 whitespace-nowrap"
                            {...props}
                          />
                        ),
                      }}
                    >
                      {selectedMR.aiSummary ||
                        selectedMR.description ||
                        "AI analysis not available."}
                    </ReactMarkdown>
                  </div>

                  {selectedMR.aiIssues.length > 0 && (
                    <div className="mt-4 space-y-2 relative z-10">
                      <p className="text-xs font-bold text-rose-400 uppercase tracking-wider mb-2">
                        Action Required
                      </p>
                      {selectedMR.aiIssues.map((issue, idx) => (
                        <div
                          key={idx}
                          className="flex items-start gap-2 text-sm text-slate-300 bg-rose-500/10 p-3 rounded-lg border border-rose-500/20"
                        >
                          <svg
                            className="w-4 h-4 text-rose-400 shrink-0 mt-0.5"
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
                          <span>{issue}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* --- FEEDBACK SYSTEM UI --- */}
                <div className="bg-slate-950/80 p-4 border-t border-slate-800/80 transition-all duration-300">
                  {feedback.submitted ? (
                    <div className="flex items-center gap-2 text-emerald-400 text-sm font-medium py-2">
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
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                      Thanks for helping improve Gatekeeper's analysis.
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-slate-400">
                          {selectedMR.isAutoFix
                            ? "Rate this generated auto-fix"
                            : "Rate this AI analysis"}
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleVote("helpful")}
                            className={`p-2 rounded-lg transition-all border ${feedback.vote === "helpful" ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-400" : "bg-slate-800 border-slate-700 text-slate-400 hover:text-emerald-400 hover:border-emerald-500/30 hover:bg-slate-800/80"}`}
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
                                d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5"
                              />
                            </svg>
                          </button>
                          <button
                            onClick={() => handleVote("unhelpful")}
                            className={`p-2 rounded-lg transition-all border ${feedback.vote === "unhelpful" ? "bg-rose-500/20 border-rose-500/50 text-rose-400" : "bg-slate-800 border-slate-700 text-slate-400 hover:text-rose-400 hover:border-rose-500/30 hover:bg-slate-800/80"}`}
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
                                d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018a2 2 0 01.485.06l3.76.94m-7 10v5a2 2 0 002 2h.096c.5 0 .905-.405.905-.904 0-.715.211-1.413.608-2.008L17 13V4m-7 10h2m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2.5"
                              />
                            </svg>
                          </button>
                        </div>
                      </div>

                      {feedback.vote && (
                        <div className="animate-in fade-in slide-in-from-top-2 duration-300">
                          <textarea
                            className="w-full bg-slate-900 border border-slate-700 rounded-xl p-3 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-[#FC6D26] focus:ring-1 focus:ring-[#FC6D26] resize-none"
                            rows="2"
                            placeholder={
                              feedback.vote === "helpful"
                                ? "What did Gatekeeper get right?"
                                : "What did Gatekeeper miss or misunderstand?"
                            }
                            value={feedback.text}
                            onChange={(e) =>
                              setFeedback({ ...feedback, text: e.target.value })
                            }
                          ></textarea>
                          <div className="flex justify-end mt-2">
                            <button
                              onClick={submitFeedback}
                              className="bg-slate-700 hover:bg-slate-600 text-white text-xs font-medium py-1.5 px-4 rounded-lg transition-colors"
                            >
                              Submit
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-slate-100 bg-slate-50/50 flex items-center justify-between">
              {selectedMR.status === "Approved" ? (
                <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wide bg-emerald-100/80 text-emerald-700 border border-emerald-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>{" "}
                  Ready to Merge
                </span>
              ) : selectedMR.status === "Reviewing" ? (
                <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wide bg-blue-100/80 text-blue-700 border border-blue-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></span>{" "}
                  Analyzing
                </span>
              ) : (
                <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wide bg-rose-100/80 text-rose-700 border border-rose-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>{" "}
                  Action Required
                </span>
              )}

              <div className="flex gap-3">
                <button
                  onClick={closeModal}
                  className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
                >
                  Close
                </button>
                <a
                  href={selectedMR.web_url || "#"}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="bg-[#FC6D26] hover:bg-[#E24329] text-white font-medium py-2 px-5 rounded-xl transition-all shadow-md flex items-center gap-2 text-sm"
                >
                  View in GitLab
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
                      d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                    />
                  </svg>
                </a>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RepoDetails;
