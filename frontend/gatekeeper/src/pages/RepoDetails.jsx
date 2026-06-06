import React, { useState, useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import {
  useRepository,
  useRepositoryMRs,
  useSubmitFeedback,
  useMRProgressLogs,
  useUpdateRepositoryCredentials,
} from "../services/queries";
import { formatLastSync } from "../utils/formatLastSync";
import { SentryIntegration } from "../components/SentryIntegration";

const RepoDetails = () => {
  const { id } = useParams();
  const [selectedMR, setSelectedMR] = useState(null);
  const [showLogs, setShowLogs] = useState(false);
  const [feedback, setFeedback] = useState({
    vote: null,
    text: "",
    submitted: false,
  });
  const [credentialModal, setCredentialModal] = useState({
    isOpen: false,
    field: null,
    value: "",
  });
  const [branchCredsModal, setBranchCredsModal] = useState({
    isOpen: false,
    branch: "",
    mongodb_uri: "",
    fivetran_api_key: "",
    fivetran_api_secret: "",
    enabled: false,
  });
  const [showBranchMongoUriModal, setShowBranchMongoUriModal] = useState(false);
  const [showBranchFivetranSecretModal, setShowBranchFivetranSecretModal] =
    useState(false);

  // Reset feedback state when selected MR changes
  useEffect(() => {
    if (selectedMR) {
      setFeedback({
        vote: null,
        text: "",
        submitted: selectedMR.userHasRated || false,
      });
    }
  }, [selectedMR]);

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

  // Feedback mutation
  const feedbackMutation = useSubmitFeedback();

  // Credentials update mutation
  const credentialsMutation = useUpdateRepositoryCredentials();

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
      fixes_merged: "0%",
    },
    vectorAnalysis: {
      security: "0%",
      performance: "0%",
      complexity: "0%",
    },
  };

  // Map backend stats to frontend format
  const stats = {
    mrsReviewed: repoData.metrics?.mrs_reviewed || repoMRs.length,
    avgTime: repoData.metrics?.avg_review_time || "0s",
    autoFixes: repoData.metrics?.auto_fixes_proposed || 0,
    fixes_merged: repoData.metrics?.fixes_merged || "0%",
  };

  const repoMRsList = repoMRs || [];

  // Group MRs: separate original MRs from auto-fix MRs
  const originalMRs = repoMRsList.filter((mr) => !mr.isAutoFix);
  const autoFixMRs = repoMRsList.filter((mr) => mr.isAutoFix);

  // Create a map of auto-fix MRs by their original MR ID
  const autoFixMRsByOriginal = {};
  autoFixMRs.forEach((autoFixMR) => {
    const originalMrIid = autoFixMR.autoFixFor;
    if (originalMrIid) {
      if (!autoFixMRsByOriginal[originalMrIid]) {
        autoFixMRsByOriginal[originalMrIid] = [];
      }
      autoFixMRsByOriginal[originalMrIid].push(autoFixMR);
    }
  });

  // Connection status from repo data (computed after repoData is available)
  const connectionStatus = {
    mongodb: !!repoData.mongodb_uri,
    fivetran: !!(repoData.fivetran_api_key && repoData.fivetran_api_secret),
    fivetranKey: !!repoData.fivetran_api_key,
    fivetranSecret: !!repoData.fivetran_api_secret,
    credentialsEncrypted: repoData.credentials_encrypted || false,
  };

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

  // Credential update handlers
  const openCredentialModal = (field, currentValue) => {
    if (field === "fivetranKey" || field === "fivetranSecret") {
      // For Fivetran, open modal with both fields
      setCredentialModal({
        isOpen: true,
        field: "fivetran",
        value: {
          apiKey: repoData.fivetran_api_key || "",
          apiSecret: repoData.fivetran_api_secret || "",
        },
      });
    } else {
      setCredentialModal({
        isOpen: true,
        field,
        value: currentValue || "",
      });
    }
  };

  const closeCredentialModal = () => {
    setCredentialModal({
      isOpen: false,
      field: null,
      value: "",
    });
  };

  const submitCredentialUpdate = async () => {
    try {
      const data = {};
      if (credentialModal.field === "mongodb") {
        data.mongodb_uri = credentialModal.value;
        // Preserve existing values
        data.fivetran_api_key = repoData.fivetran_api_key || "";
        data.fivetran_api_secret = repoData.fivetran_api_secret || "";
      } else if (credentialModal.field === "fivetran") {
        data.fivetran_api_key = credentialModal.value.apiKey;
        data.fivetran_api_secret = credentialModal.value.apiSecret;
        data.mongodb_uri = repoData.mongodb_uri || "";
      }

      await credentialsMutation.mutateAsync({
        repoId: id,
        data,
      });
      closeCredentialModal();
    } catch (err) {
      console.error("Failed to update credential:", err);
    }
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
                • Last synced {formatLastSync(repo.last_sync)}
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
            Approved Autofixes
          </p>
          <p className="text-2xl font-bold text-emerald-600">
            {stats.fixes_merged}
          </p>
        </div>
      </div>

      {/* Main Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* LEFT COLUMN: MR Feed */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 lg:p-8 flex flex-col h-full">
            {/* Header */}
            <div className="flex justify-between items-center mb-6 pb-4 border-b border-slate-100/50">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-slate-900 flex items-center justify-center shadow-sm">
                  <svg
                    className="w-5 h-5 text-white"
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
                <h3 className="text-lg font-bold text-slate-900 tracking-tight">
                  Merge Requests Feed
                </h3>
              </div>
              <div className="flex items-center gap-3">
                {mrsLoading && (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-[#FC6D26]"></div>
                )}
                <button className="text-xs font-bold uppercase tracking-wider text-[#FC6D26] bg-[#FC6D26]/10 px-4 py-2 rounded-xl hover:bg-[#FC6D26]/20 transition-colors flex items-center gap-1.5">
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
                      d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"
                    />
                  </svg>
                  Filter
                </button>
              </div>
            </div>

            <div className="space-y-5 flex-1">
              {repoMRsList.length === 0 ? (
                <div className="text-center py-16 flex flex-col items-center justify-center h-full">
                  <div className="w-16 h-16 bg-slate-50 border border-slate-100 rounded-full flex items-center justify-center mb-4">
                    <svg
                      className="w-8 h-8 text-slate-300"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="1.5"
                        d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
                      />
                    </svg>
                  </div>
                  <h4 className="text-base font-semibold text-slate-900 mb-1">
                    Queue is empty
                  </h4>
                  <p className="text-sm text-slate-500 max-w-xs">
                    No merge requests found. Sync your repository to fetch the
                    latest data.
                  </p>
                </div>
              ) : (
                originalMRs.map((mr, i) => {
                  // Map backend status to frontend display
                  const getStatusDisplay = (status) => {
                    switch (status) {
                      case "open":
                        return "Open";
                      case "reviewing":
                        return "Reviewing";
                      case "reviewed":
                        return "Reviewed";
                      case "merged":
                        return "Merged";
                      case "closed":
                        return "Closed";
                      case "draft":
                        return "Draft";
                      case "failed":
                        return "Failed";
                      default:
                        return "Open";
                    }
                  };

                  const statusDisplay = getStatusDisplay(mr.status);
                  const autoFixMrsForThisMR =
                    autoFixMRsByOriginal[mr.iid] ||
                    autoFixMRsByOriginal[mr.gitlab_mr_id] ||
                    [];

                  return (
                    <div key={i} className="relative group/thread">
                      {/* Original MR Card */}
                      <div
                        onClick={() => setSelectedMR(mr)}
                        className="group p-4 rounded-2xl bg-white border border-slate-100 hover:border-slate-200 hover:shadow-md transition-all duration-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4 cursor-pointer relative z-10"
                      >
                        <div className="flex items-start sm:items-center gap-4 min-w-0 flex-1">
                          <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-center shrink-0 group-hover:bg-slate-100 transition-colors">
                            <svg
                              className="w-5 h-5 text-slate-400 group-hover:text-slate-600 transition-colors"
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

                          <div className="min-w-0 flex-1">
                            <div className="text-sm font-bold text-slate-900 mb-1.5 flex flex-wrap items-center gap-2">
                              <span className="truncate">{mr.title}</span>
                              {autoFixMrsForThisMR.length > 0 && (
                                <span className="px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest bg-[#FC6D26]/10 text-[#FC6D26] rounded border border-[#FC6D26]/20 shrink-0">
                                  {autoFixMrsForThisMR.length} Auto-Fix
                                  {autoFixMrsForThisMR.length > 1 ? "es" : ""}
                                </span>
                              )}
                            </div>
                            <div className="flex flex-wrap items-center gap-2 text-xs font-mono text-slate-500">
                              <span
                                className="bg-slate-100 px-1.5 py-0.5 rounded text-slate-600 border border-slate-200/60 truncate max-w-[120px]"
                                title={mr.branch}
                              >
                                {mr.branch}
                              </span>
                              <svg
                                className="w-3 h-3 text-slate-300 shrink-0"
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
                              <span
                                className="bg-slate-100 px-1.5 py-0.5 rounded text-slate-600 border border-slate-200/60 truncate max-w-[120px]"
                                title={mr.target}
                              >
                                {mr.target}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="flex flex-row sm:flex-col items-center sm:items-end justify-between sm:justify-center gap-2 ml-14 sm:ml-0 shrink-0">
                          {statusDisplay === "Open" && (
                            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide bg-slate-100 text-slate-600 border border-slate-200">
                              <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>{" "}
                              Open
                            </span>
                          )}
                          {statusDisplay === "Reviewing" && (
                            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide bg-blue-50 text-blue-600 border border-blue-100">
                              <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></span>{" "}
                              Reviewing
                            </span>
                          )}
                          {statusDisplay === "Reviewed" && (
                            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide bg-emerald-50 text-emerald-600 border border-emerald-100">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>{" "}
                              Reviewed
                            </span>
                          )}
                          {statusDisplay === "Merged" && (
                            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide bg-purple-50 text-purple-600 border border-purple-100">
                              <span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span>{" "}
                              Merged
                            </span>
                          )}
                          <span className="text-[10px] text-slate-400 font-medium whitespace-nowrap">
                            {mr.id} • {mr.time}
                          </span>
                        </div>
                      </div>

                      {/* Threaded Auto-Fix MRs Block */}
                      {autoFixMrsForThisMR.length > 0 && (
                        <div className="mt-2 ml-5 sm:ml-9 pl-4 border-l-2 border-slate-200/60 space-y-3 relative pb-1">
                          <div className="absolute top-0 -left-[5px] w-2 h-2 rounded-full bg-slate-200/60"></div>

                          {autoFixMrsForThisMR.map((autoFixMR, idx) => {
                            const autoFixStatusDisplay = getStatusDisplay(
                              autoFixMR.status,
                            );
                            return (
                              <div
                                key={`${i}-autofix-${idx}`}
                                onClick={() => setSelectedMR(autoFixMR)}
                                className="group/autofix p-4 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4 cursor-pointer shadow-sm relative overflow-hidden"
                              >
                                <div className="absolute inset-0 bg-gradient-to-r from-[#FC6D26]/5 to-transparent opacity-0 group-hover/autofix:opacity-100 transition-opacity"></div>

                                {/* Left Segment: Header & Content Wrapper */}
                                <div className="flex items-start gap-3 relative z-10 flex-1 min-w-0">
                                  <div className="w-8 h-8 rounded-lg bg-[#FC6D26]/10 border border-[#FC6D26]/20 flex items-center justify-center shrink-0 mt-0.5 md:mt-0">
                                    <svg
                                      className="w-4 h-4 text-[#FC6D26]"
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

                                  <div className="min-w-0 flex-1 space-y-2">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <p className="text-sm font-semibold text-white truncate max-w-[280px] sm:max-w-[400px]">
                                        {autoFixMR.title}
                                      </p>
                                      <span className="px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-widest bg-[#FC6D26]/20 text-[#FC6D26] rounded border border-[#FC6D26]/30 shrink-0">
                                        AI Generated
                                      </span>
                                    </div>

                                    {/* Clean line layout for branch flow */}
                                    <div className="flex flex-wrap items-center gap-2 text-xs font-mono text-slate-400">
                                      <span
                                        className="bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700 truncate max-w-[150px]"
                                        title={autoFixMR.branch}
                                      >
                                        {autoFixMR.branch}
                                      </span>
                                      <svg
                                        className="w-2.5 h-2.5 text-slate-600 shrink-0"
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
                                      <span
                                        className="bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700 truncate max-w-[120px]"
                                        title={autoFixMR.target}
                                      >
                                        {autoFixMR.target}
                                      </span>
                                    </div>
                                  </div>
                                </div>

                                {/* Right Segment: Status and Meta Authorship */}
                                <div className="flex flex-row md:flex-col items-center md:items-end justify-between md:justify-center gap-2 pl-11 md:pl-0 shrink-0 relative z-10 border-t md:border-t-0 border-slate-800/60 pt-3 md:pt-0">
                                  {autoFixStatusDisplay === "Open" && (
                                    <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider bg-slate-800 text-slate-300 border border-slate-700">
                                      <span className="w-1.5 h-1.5 rounded-full bg-slate-500"></span>{" "}
                                      Open
                                    </span>
                                  )}
                                  {autoFixStatusDisplay === "Merged" && (
                                    <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider bg-purple-500/10 text-purple-400 border border-purple-500/20">
                                      <span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span>{" "}
                                      Merged
                                    </span>
                                  )}
                                  <div className="text-[10px] text-slate-500 font-medium whitespace-nowrap truncate max-w-[180px]">
                                    <span
                                      className="text-[#FC6D26] font-semibold"
                                      title={autoFixMR.author}
                                    >
                                      {autoFixMR.author}
                                    </span>{" "}
                                    • {autoFixMR.time}
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
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

          {/* Active Policies - Connection Status */}
          <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 lg:p-8">
            <div className="flex justify-between items-center mb-5">
              <h3 className="text-lg font-bold text-slate-900">
                Active Policies
              </h3>
              {connectionStatus.credentialsEncrypted && (
                <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-100/80 text-emerald-700 border border-emerald-200">
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
                      d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                    />
                  </svg>
                  <span className="text-[10px] font-bold uppercase tracking-wide">
                    Encrypted
                  </span>
                </div>
              )}
            </div>
            <div className="space-y-3">
              {/* MongoDB Connection */}
              <div className="flex items-start gap-3">
                <div
                  className={`mt-0.5 shrink-0 w-5 h-5 rounded flex items-center justify-center ${connectionStatus.mongodb ? "bg-emerald-100 text-emerald-600" : "bg-slate-100 text-slate-300"}`}
                >
                  {connectionStatus.mongodb ? (
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
                <div className="flex-1">
                  <span
                    className={`text-sm ${connectionStatus.mongodb ? "text-slate-700 font-medium" : "text-slate-400"}`}
                  >
                    MongoDB Check
                  </span>
                  {connectionStatus.mongodb && (
                    <p className="text-xs text-slate-500 mt-0.5">
                      Schema inspection enabled
                    </p>
                  )}
                </div>
                <button
                  onClick={() =>
                    openCredentialModal("mongodb", repoData.mongodb_uri)
                  }
                  className="text-slate-400 hover:text-[#FC6D26] transition-colors p-1 rounded hover:bg-slate-100"
                  title="Update MongoDB URI"
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
                      d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                    />
                  </svg>
                </button>
              </div>

              {/* Fivetran Integration */}
              <div className="flex items-start gap-3">
                <div
                  className={`mt-0.5 shrink-0 w-5 h-5 rounded flex items-center justify-center ${connectionStatus.fivetran ? "bg-emerald-100 text-emerald-600" : "bg-slate-100 text-slate-300"}`}
                >
                  {connectionStatus.fivetran ? (
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
                <div className="flex-1">
                  <span
                    className={`text-sm ${connectionStatus.fivetran ? "text-slate-700 font-medium" : "text-slate-400"}`}
                  >
                    Fivetran Integration
                  </span>
                  {connectionStatus.fivetran ? (
                    <p className="text-xs text-slate-500 mt-0.5">
                      Connected (API Key + Secret configured)
                    </p>
                  ) : connectionStatus.fivetranKey ||
                    connectionStatus.fivetranSecret ? (
                    <p className="text-xs text-amber-600 mt-0.5">
                      Incomplete configuration
                    </p>
                  ) : null}
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() =>
                      openCredentialModal(
                        "fivetranSecret",
                        repoData.fivetran_api_secret,
                      )
                    }
                    className="text-slate-400 hover:text-[#FC6D26] transition-colors p-1 rounded hover:bg-slate-100"
                    title="Update Fivetran API Secret"
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
                        d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                      />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Sentry Integration */}
          <SentryIntegration repoId={id} />

          {/* Monitored Branches - Credentials Overrides */}
          <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 lg:p-8">
            <div className="flex justify-between items-center mb-5">
              <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
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
                    d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"
                  />
                </svg>
                Monitored Branches
              </h3>
            </div>
            <p className="text-xs text-slate-500 mb-4 leading-relaxed">
              Configure custom database credentials per branch for schema drift
              checks.
            </p>
            {console.log("repoData", repoData)}
            <div className="space-y-3">
              {repoData &&
                repoData.target_branches &&
                repoData.target_branches.length > 0 &&
                repoData.target_branches.map((branch) => {
                  const branchCreds = repoData.branch_credentials?.[branch];
                  const hasOverride =
                    branchCreds &&
                    (branchCreds.mongodb_uri ||
                      branchCreds.fivetran_api_key ||
                      branchCreds.fivetran_api_secret);

                  return (
                    <div
                      key={branch}
                      className="flex items-center justify-between p-3.5 bg-slate-50/50 border border-slate-100 rounded-2xl"
                    >
                      <div className="flex flex-col gap-1.5">
                        <span className="text-xs font-mono font-bold text-slate-800">
                          {branch}
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full inline-block w-fit border uppercase tracking-wider ${
                            hasOverride
                              ? "bg-emerald-50 text-emerald-700 border-emerald-100"
                              : "bg-slate-100 text-slate-500 border-slate-200"
                          }`}
                        >
                          {hasOverride ? "Override Active" : "Using Defaults"}
                        </span>
                      </div>

                      <button
                        onClick={() => {
                          const currentCreds =
                            repoData.branch_credentials?.[branch] || {};
                          setBranchCredsModal({
                            isOpen: true,
                            branch,
                            mongodb_uri: currentCreds.mongodb_uri || "",
                            fivetran_api_key:
                              currentCreds.fivetran_api_key || "",
                            fivetran_api_secret:
                              currentCreds.fivetran_api_secret || "",
                            enabled: !!(
                              currentCreds.mongodb_uri ||
                              currentCreds.fivetran_api_key ||
                              currentCreds.fivetran_api_secret
                            ),
                          });
                          setShowBranchMongoUriModal(false);
                          setShowBranchFivetranSecretModal(false);
                        }}
                        className="flex items-center gap-1 text-xs font-bold text-slate-600 hover:text-[#FC6D26] bg-white hover:bg-slate-50 px-3 py-1.5 border border-slate-200 rounded-xl shadow-sm transition-colors"
                      >
                        Configure
                      </button>
                    </div>
                  );
                })}
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

              {/* Progress Logs Section - Show for reviewing/reviewed MRs */}
              {(selectedMR.status === "reviewing" ||
                selectedMR.status === "reviewed" ||
                selectedMR.status === "Reviewing" ||
                selectedMR.status === "Reviewed") && (
                <ProgressLogsViewer
                  repoId={id}
                  mrIid={selectedMR.iid || selectedMR.gitlab_mr_id}
                  isReviewing={
                    selectedMR.status === "reviewing" ||
                    selectedMR.status === "Reviewing"
                  }
                />
              )}

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
                  {selectedMR.userHasRated ? (
                    <div className="flex items-center gap-2 text-slate-400 text-sm font-medium py-2">
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
                      You already rated this analysis as {selectedMR.userVote}.
                    </div>
                  ) : feedback.submitted ? (
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
              {selectedMR.status === "Approved" ||
              selectedMR.status === "reviewed" ? (
                <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wide bg-emerald-100/80 text-emerald-700 border border-emerald-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>{" "}
                  Ready to Merge
                </span>
              ) : selectedMR.status === "Reviewing" ||
                selectedMR.status === "reviewing" ? (
                <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wide bg-blue-100/80 text-blue-700 border border-blue-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></span>{" "}
                  Analyzing
                </span>
              ) : selectedMR.status === "Failed" ||
                selectedMR.status === "failed" ? (
                <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wide bg-rose-100/80 text-rose-700 border border-rose-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>{" "}
                  Analysis Failed
                </span>
              ) : selectedMR.status === "Merged" ||
                selectedMR.status === "merged" ? (
                <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wide bg-purple-100/80 text-purple-700 border border-purple-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span>{" "}
                  Merged
                </span>
              ) : (
                <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wide bg-slate-100/80 text-slate-700 border border-slate-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-500"></span>{" "}
                  {selectedMR.status || "Open"}
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

      {/* =========================================
          CREDENTIAL UPDATE MODAL
          ========================================= */}
      {credentialModal.isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6">
          <div
            className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity"
            onClick={closeCredentialModal}
          ></div>

          <div className="relative w-full max-w-md bg-white/95 backdrop-blur-2xl border border-white rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-white/50">
              <h2 className="text-lg font-bold text-slate-900">
                {credentialModal.field === "mongodb" && "Update MongoDB URI"}
                {credentialModal.field === "fivetran" &&
                  "Update Fivetran Credentials"}
              </h2>
              <button
                onClick={closeCredentialModal}
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
            <div className="p-6">
              {/* MongoDB - Single field */}
              {credentialModal.field === "mongodb" && (
                <>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    MongoDB Connection URI
                  </label>
                  <input
                    type="text"
                    value={credentialModal.value}
                    onChange={(e) =>
                      setCredentialModal({
                        ...credentialModal,
                        value: e.target.value,
                      })
                    }
                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:outline-none focus:border-[#FC6D26] focus:ring-1 focus:ring-[#FC6D26] transition-all"
                    placeholder="mongodb://localhost:27017"
                    autoFocus
                  />
                </>
              )}

              {/* Fivetran - Two fields */}
              {credentialModal.field === "fivetran" && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">
                      Fivetran API Key
                    </label>
                    <input
                      type="password"
                      value={credentialModal.value.apiKey}
                      onChange={(e) =>
                        setCredentialModal({
                          ...credentialModal,
                          value: {
                            ...credentialModal.value,
                            apiKey: e.target.value,
                          },
                        })
                      }
                      className="w-full px-4 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:outline-none focus:border-[#FC6D26] focus:ring-1 focus:ring-[#FC6D26] transition-all"
                      placeholder="Enter your API key"
                      autoFocus
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">
                      Fivetran API Secret
                    </label>
                    <input
                      type="password"
                      value={credentialModal.value.apiSecret}
                      onChange={(e) =>
                        setCredentialModal({
                          ...credentialModal,
                          value: {
                            ...credentialModal.value,
                            apiSecret: e.target.value,
                          },
                        })
                      }
                      className="w-full px-4 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:outline-none focus:border-[#FC6D26] focus:ring-1 focus:ring-[#FC6D26] transition-all"
                      placeholder="Enter your API secret"
                    />
                  </div>
                </div>
              )}
              {connectionStatus.credentialsEncrypted && (
                <p className="text-xs text-slate-500 mt-2 flex items-center gap-1">
                  <svg
                    className="w-3 h-3 text-emerald-500"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                    />
                  </svg>
                  Credentials are encrypted at rest
                </p>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-slate-100 bg-slate-50/50 flex items-center justify-end gap-3">
              <button
                onClick={closeCredentialModal}
                className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={submitCredentialUpdate}
                disabled={
                  credentialsMutation.isPending ||
                  (credentialModal.field === "mongodb" &&
                    !credentialModal.value.trim()) ||
                  (credentialModal.field === "fivetran" &&
                    (!credentialModal.value.apiKey.trim() ||
                      !credentialModal.value.apiSecret.trim()))
                }
                className="bg-[#FC6D26] hover:bg-[#E24329] text-white font-medium py-2 px-5 rounded-xl transition-all shadow-md flex items-center gap-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {credentialsMutation.isPending ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    Updating...
                  </>
                ) : (
                  "Update"
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =========================================
          BRANCH CREDENTIAL UPDATE MODAL
          ========================================= */}
      {branchCredsModal.isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6">
          <div
            className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity"
            onClick={() =>
              setBranchCredsModal({ ...branchCredsModal, isOpen: false })
            }
          ></div>

          <div className="relative w-full max-w-md bg-white/95 backdrop-blur-2xl border border-white rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-white/50">
              <div className="flex flex-col">
                <h2 className="text-lg font-bold text-slate-900">
                  Configure Override
                </h2>
                <span className="text-xs font-mono font-bold text-[#FC6D26] mt-0.5">
                  Branch: {branchCredsModal.branch}
                </span>
              </div>
              <button
                onClick={() =>
                  setBranchCredsModal({ ...branchCredsModal, isOpen: false })
                }
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
            <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
              {/* Enable Override Toggle */}
              <div className="flex items-center justify-between p-3.5 bg-slate-50 rounded-xl border border-slate-100 mb-2">
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-slate-700">
                    Enable Custom Credentials
                  </span>
                  <span className="text-[10px] text-slate-400">
                    Override repository-level defaults for this branch
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={branchCredsModal.enabled}
                  onChange={(e) =>
                    setBranchCredsModal({
                      ...branchCredsModal,
                      enabled: e.target.checked,
                    })
                  }
                  className="w-4 h-4 text-[#FC6D26] focus:ring-[#FC6D26]/30 border-slate-300 rounded cursor-pointer"
                />
              </div>

              {branchCredsModal.enabled && (
                <div className="space-y-4 pt-1 animate-in fade-in slide-in-from-top-2 duration-200">
                  {/* MongoDB Connection URI Override */}
                  <div>
                    <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">
                      MongoDB URI Override
                    </label>
                    <div className="relative">
                      <input
                        type={showBranchMongoUriModal ? "text" : "password"}
                        value={branchCredsModal.mongodb_uri}
                        onChange={(e) =>
                          setBranchCredsModal({
                            ...branchCredsModal,
                            mongodb_uri: e.target.value,
                          })
                        }
                        className="w-full px-4 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:outline-none focus:border-[#FC6D26] focus:ring-1 focus:ring-[#FC6D26] text-xs font-mono transition-all"
                        placeholder="mongodb://username:password@host:port/db"
                      />
                      <button
                        type="button"
                        onClick={() =>
                          setShowBranchMongoUriModal(!showBranchMongoUriModal)
                        }
                        className="absolute right-3.5 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-slate-600 focus:outline-none transition-colors duration-200"
                      >
                        {showBranchMongoUriModal ? (
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
                              d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"
                            />
                          </svg>
                        ) : (
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
                              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                            />
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth="2"
                              d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                            />
                          </svg>
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Fivetran API Key Override */}
                  <div>
                    <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">
                      Fivetran API Key Override
                    </label>
                    <input
                      type="text"
                      value={branchCredsModal.fivetran_api_key}
                      onChange={(e) =>
                        setBranchCredsModal({
                          ...branchCredsModal,
                          fivetran_api_key: e.target.value,
                        })
                      }
                      className="w-full px-4 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:outline-none focus:border-[#FC6D26] focus:ring-1 focus:ring-[#FC6D26] text-xs font-mono transition-all"
                      placeholder="Enter Fivetran API Key"
                    />
                  </div>

                  {/* Fivetran API Secret Override */}
                  <div>
                    <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">
                      Fivetran Secret Override
                    </label>
                    <div className="relative">
                      <input
                        type={
                          showBranchFivetranSecretModal ? "text" : "password"
                        }
                        value={branchCredsModal.fivetran_api_secret}
                        onChange={(e) =>
                          setBranchCredsModal({
                            ...branchCredsModal,
                            fivetran_api_secret: e.target.value,
                          })
                        }
                        className="w-full px-4 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:outline-none focus:border-[#FC6D26] focus:ring-1 focus:ring-[#FC6D26] text-xs font-mono transition-all"
                        placeholder="Enter Fivetran API Secret"
                      />
                      <button
                        type="button"
                        onClick={() =>
                          setShowBranchFivetranSecretModal(
                            !showBranchFivetranSecretModal,
                          )
                        }
                        className="absolute right-3.5 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-slate-600 focus:outline-none transition-colors duration-200"
                      >
                        {showBranchFivetranSecretModal ? (
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
                              d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"
                            />
                          </svg>
                        ) : (
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
                              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                            />
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth="2"
                              d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                            />
                          </svg>
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-slate-100 bg-slate-50/50 flex items-center justify-between gap-3">
              {/* Left side: Delete override button */}
              <div>
                {repoData.branch_credentials?.[branchCredsModal.branch] && (
                  <button
                    onClick={async () => {
                      try {
                        const remainingBranchCreds = {
                          ...repoData.branch_credentials,
                        };
                        delete remainingBranchCreds[branchCredsModal.branch];

                        await credentialsMutation.mutateAsync({
                          repoId: id,
                          data: {
                            branch_credentials: remainingBranchCreds,
                          },
                        });
                        setBranchCredsModal({
                          ...branchCredsModal,
                          isOpen: false,
                        });
                      } catch (err) {
                        console.error("Failed to delete branch override:", err);
                      }
                    }}
                    disabled={credentialsMutation.isPending}
                    className="text-xs font-bold text-rose-600 hover:text-rose-700 bg-rose-50 hover:bg-rose-100 px-3 py-2 border border-rose-100 rounded-xl transition-all"
                  >
                    Delete Override
                  </button>
                )}
              </div>

              {/* Right side: Save & Cancel */}
              <div className="flex items-center gap-3">
                <button
                  onClick={() =>
                    setBranchCredsModal({ ...branchCredsModal, isOpen: false })
                  }
                  className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={async () => {
                    try {
                      const currentBranchCreds =
                        { ...repoData.branch_credentials } || {};
                      if (branchCredsModal.enabled) {
                        currentBranchCreds[branchCredsModal.branch] = {
                          mongodb_uri: branchCredsModal.mongodb_uri,
                          fivetran_api_key: branchCredsModal.fivetran_api_key,
                          fivetran_api_secret:
                            branchCredsModal.fivetran_api_secret,
                        };
                      } else {
                        delete currentBranchCreds[branchCredsModal.branch];
                      }

                      await credentialsMutation.mutateAsync({
                        repoId: id,
                        data: {
                          branch_credentials: currentBranchCreds,
                        },
                      });
                      setBranchCredsModal({
                        ...branchCredsModal,
                        isOpen: false,
                      });
                    } catch (err) {
                      console.error("Failed to save branch override:", err);
                    }
                  }}
                  disabled={
                    credentialsMutation.isPending ||
                    (branchCredsModal.enabled &&
                      !branchCredsModal.mongodb_uri.trim() &&
                      !branchCredsModal.fivetran_api_key.trim() &&
                      !branchCredsModal.fivetran_api_secret.trim())
                  }
                  className="bg-[#FC6D26] hover:bg-[#E24329] text-white font-medium py-2 px-5 rounded-xl transition-all shadow-md flex items-center gap-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {credentialsMutation.isPending ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Saving...
                    </>
                  ) : (
                    "Save"
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Progress Logs Viewer Component
const ProgressLogsViewer = ({ repoId, mrIid, isReviewing }) => {
  const { data: logsData, isLoading } = useMRProgressLogs(repoId, mrIid, {
    refetchInterval: isReviewing ? 2000 : false, // Poll every 2s when reviewing
  });
  const logs = logsData?.logs || [];

  if (logs.length === 0 && !isLoading) {
    return null;
  }

  return (
    <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden">
      <div className="px-4 py-3 bg-slate-800/50 border-b border-slate-700/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isReviewing && (
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
          )}
          <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Analysis Progress
          </span>
        </div>
        {isReviewing && (
          <span className="text-[10px] text-blue-400 font-medium">Live</span>
        )}
      </div>
      <div className="p-4 max-h-48 overflow-y-auto space-y-2 font-mono text-xs">
        {logs.map((log, idx) => (
          <div key={idx} className="flex items-start gap-2">
            <span className="text-slate-500 shrink-0">
              {new Date(log.timestamp).toLocaleTimeString("en-US", {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </span>
            <span
              className={`flex-1 ${
                log.status === "running"
                  ? "text-blue-400"
                  : log.status === "completed"
                    ? "text-emerald-400"
                    : log.status === "failed"
                      ? "text-rose-400"
                      : "text-slate-300"
              }`}
            >
              {log.message}
            </span>
          </div>
        ))}
        {isLoading && (
          <div className="text-slate-500 text-center py-2">Loading logs...</div>
        )}
      </div>
    </div>
  );
};

export default RepoDetails;
