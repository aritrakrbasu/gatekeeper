/**
 * ConnectRepositoryModal Component
 *
 * Modal for searching, scanning, and onboarding GitLab repositories.
 * Uses React Query for optimized caching, credential scanning, and secure onboarding.
 * Enhanced with branch selection and webhook installation.
 */

import React, { useState, useEffect } from "react";
import {
  useAvailableRepositories,
  useScanRepository,
  useOnboardRepository,
  useRepositoryBranches,
  useInstallWebhook,
} from "../services/queries";
import { useDebounce } from "../hooks/useDebounce";
import BranchSelector from "./BranchSelector";

const ConnectRepositoryModal = ({ isOpen, onClose, onConnect }) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [connectedIds, setConnectedIds] = useState(new Set());

  // Onboarding workflow states
  const [step, setStep] = useState("list"); // "list" | "branches" | "webhook-confirm" | "onboard"
  const [selectedRepo, setSelectedRepo] = useState(null);

  // Branch selection state
  const [selectedBranches, setSelectedBranches] = useState(new Set());
  const [defaultBranch, setDefaultBranch] = useState("main");

  // Webhook state
  const [webhookUrl, setWebhookUrl] = useState("");
  const [installWebhook, setInstallWebhook] = useState(true);

  // Credential state
  const [mongodbUri, setMongodbUri] = useState("");
  const [fivetranApiKey, setFivetranApiKey] = useState("");
  const [fivetranApiSecret, setFivetranApiSecret] = useState("");
  const [encryptCredentials, setEncryptCredentials] = useState(true);
  const [showMongodbUri, setShowMongodbUri] = useState(false);
  const [showFivetranApiSecret, setShowFivetranApiSecret] = useState(false);

  const [isScanning, setIsScanning] = useState(false);
  const [scanResults, setScanResults] = useState(null);
  const [onboardingError, setOnboardingError] = useState(null);
  const [webhookError, setWebhookError] = useState(null);

  // Debounce the search query to reduce API calls (500ms delay)
  const debouncedSearchQuery = useDebounce(searchQuery, 500);

  // Use React Query hook for fetching available repositories
  const {
    data: repositories = [],
    isLoading,
    error,
    refetch,
  } = useAvailableRepositories(
    debouncedSearchQuery,
    isOpen && step === "list", // Only fetch list when modal is open and on list step
  );

  // Mutations for scanning, onboarding, and webhook installation
  const scanMutation = useScanRepository();
  const onboardMutation = useOnboardRepository();
  const installWebhookMutation = useInstallWebhook();

  // Fetch branches for the selected repository
  const {
    data: branches = [],
    isLoading: branchesLoading,
    refetch: refetchBranches,
  } = useRepositoryBranches(selectedRepo?.id, isOpen && step === "branches");

  // Reset states on close
  const handleClose = () => {
    setStep("list");
    setSelectedRepo(null);
    setSearchQuery("");
    setSelectedBranches(new Set());
    setDefaultBranch("main");
    setWebhookUrl("");
    setInstallWebhook(true);
    setMongodbUri("");
    setFivetranApiKey("");
    setFivetranApiSecret("");
    setEncryptCredentials(true);
    setScanResults(null);
    setIsScanning(false);
    setOnboardingError(null);
    setWebhookError(null);
    setShowMongodbUri(false);
    setShowFivetranApiSecret(false);
    onClose();
  };

  // Toggle branch selection
  const toggleBranch = (branchName) => {
    setSelectedBranches((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(branchName)) {
        newSet.delete(branchName);
      } else {
        newSet.add(branchName);
      }
      return newSet;
    });
  };

  // Start branch selection
  const startBranchSelection = async (repo) => {
    setSelectedRepo(repo);
    setStep("branches");
    setSelectedBranches(new Set());
    setDefaultBranch("main");
    // Branches will be fetched by the useRepositoryBranches hook
  };

  // Handle webhook installation
  const handleWebhookInstall = async () => {
    setWebhookError(null);

    try {
      const result = await installWebhookMutation.mutateAsync({
        repoId: selectedRepo.id,
        monitoredBranches: Array.from(selectedBranches),
        webhookUrl: webhookUrl || undefined,
      });

      console.log("Webhook installed successfully:", result);

      // Proceed to onboarding step
      setStep("onboard");
      setIsScanning(true);
      setMongodbUri("");
      setFivetranApiKey("");
      setFivetranApiSecret("");
      setScanResults(null);
      setOnboardingError(null);

      // Auto-scan repository
      try {
        const results = await scanMutation.mutateAsync(selectedRepo.id);
        setScanResults(results);
        if (results.mongodb_uri) {
          setMongodbUri(results.mongodb_uri);
        }
        if (results.fivetran_api_key) {
          setFivetranApiKey(results.fivetran_api_key);
        }
        if (results.fivetran_api_secret) {
          setFivetranApiSecret(results.fivetran_api_secret);
        }
      } catch (err) {
        console.error("Auto-scan failed:", err);
        setScanResults({
          error:
            "Failed to automatically scan repository files. You can enter details manually.",
          detected_in_files: [],
        });
      } finally {
        setIsScanning(false);
      }
    } catch (err) {
      console.error("Webhook installation failed:", err);
      setWebhookError(
        err.message ||
          "Failed to install webhook. You can connect without a webhook.",
      );
    }
  };

  // Skip webhook installation and go directly to onboarding
  const skipWebhook = () => {
    setStep("onboard");
    setIsScanning(true);
    setMongodbUri("");
    setFivetranApiKey("");
    setFivetranApiSecret("");
    setScanResults(null);
    setOnboardingError(null);

    // Auto-scan repository
    scanMutation
      .mutateAsync(selectedRepo.id)
      .then((results) => {
        setScanResults(results);
        if (results.mongodb_uri) {
          setMongodbUri(results.mongodb_uri);
        }
        if (results.fivetran_api_key) {
          setFivetranApiKey(results.fivetran_api_key);
        }
        if (results.fivetran_api_secret) {
          setFivetranApiSecret(results.fivetran_api_secret);
        }
      })
      .catch((err) => {
        console.error("Auto-scan failed:", err);
        setScanResults({
          error:
            "Failed to automatically scan repository files. You can enter details manually.",
          detected_in_files: [],
        });
      })
      .finally(() => {
        setIsScanning(false);
      });
  };

  // Submit onboarding details
  const handleOnboardSubmit = async (e) => {
    e.preventDefault();
    if (!selectedRepo) return;

    setOnboardingError(null);
    try {
      await onboardMutation.mutateAsync({
        repoId: selectedRepo.id,
        data: {
          mongodb_uri: mongodbUri,
          fivetran_api_key: fivetranApiKey,
          fivetran_api_secret: fivetranApiSecret,
          encrypt_credentials: encryptCredentials,
          monitored_branches: Array.from(selectedBranches),
          branch_filter_enabled: selectedBranches.size > 0,
        },
      });

      setConnectedIds(new Set([...connectedIds, selectedRepo.id]));
      onConnect && onConnect(selectedRepo);
      handleClose();
    } catch (err) {
      console.error("Onboarding failed:", err);
      setOnboardingError(
        err.message ||
          "Failed to onboard repository. Please check credentials.",
      );
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 transition-all duration-300">
      <div className="bg-white rounded-[2rem] border border-slate-100 shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Render List Step */}
        {step === "list" && (
          <>
            {/* Header */}
            <div className="p-6 border-b border-slate-100">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-xl font-bold text-slate-950">
                    Connect Repository
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Select a GitLab project to integrate with Gatekeeper
                  </p>
                </div>
                <button
                  onClick={handleClose}
                  className="w-8 h-8 rounded-full bg-slate-50 hover:bg-slate-100 flex items-center justify-center text-slate-500 hover:text-slate-800 transition-colors"
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
                      strokeWidth="2.5"
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>

              {/* Search */}
              <div className="relative">
                <svg
                  className="w-4 h-4 text-slate-400 absolute left-4 top-1/2 transform -translate-y-1/2"
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
                  placeholder="Search your GitLab repositories..."
                  className="w-full pl-11 pr-4 py-3 bg-slate-50 border border-slate-100 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#FC6D26]/20 focus:border-[#FC6D26] text-sm text-slate-800 placeholder-slate-400 transition-all focus:bg-white"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
            </div>

            {/* List Content */}
            <div className="flex-1 overflow-y-auto p-6 bg-slate-50/30">
              {isLoading && repositories.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20">
                  <div className="animate-spin rounded-full h-8 w-8 border-2 border-[#FC6D26] border-t-transparent mb-3"></div>
                  <p className="text-xs text-slate-400">
                    Loading your repositories...
                  </p>
                </div>
              ) : error ? (
                <div className="bg-rose-50 border border-rose-100 rounded-xl p-4">
                  <div className="flex items-center gap-3">
                    <svg
                      className="w-5 h-5 text-rose-500"
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
                    <p className="text-sm text-rose-700">
                      {error.message || "Failed to load GitLab repositories"}
                    </p>
                  </div>
                </div>
              ) : repositories.length === 0 ? (
                <div className="text-center py-16">
                  <div className="w-12 h-12 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-3">
                    <svg
                      className="w-6 h-6 text-slate-400"
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
                  <h3 className="text-sm font-semibold text-slate-800 mb-1">
                    {debouncedSearchQuery
                      ? "No repositories found"
                      : "All repositories connected"}
                  </h3>
                  <p className="text-xs text-slate-400 max-w-xs mx-auto">
                    {debouncedSearchQuery
                      ? "Try searching for a different keyword or check spelling"
                      : "You have successfully linked all eligible GitLab repositories to Gatekeeper"}
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {repositories.map((repo) => (
                    <div
                      key={repo.id}
                      className="flex items-center justify-between p-4 bg-white border border-slate-100 rounded-2xl hover:shadow-md hover:border-slate-200/80 transition-all group"
                    >
                      <div className="flex items-center gap-4 flex-1 min-w-0">
                        {repo.avatar_url ? (
                          <img
                            src={repo.avatar_url}
                            alt={repo.name}
                            className="w-10 h-10 rounded-xl object-cover border border-slate-100"
                          />
                        ) : (
                          <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-center shrink-0">
                            <svg
                              className="w-5 h-5 text-[#FC6D26]"
                              viewBox="0 0 24 24"
                              fill="currentColor"
                            >
                              <path d="M23.955 13.587l-1.342-4.135-2.664-8.189c-.135-.423-.73-.423-.867 0L16.418 9.45H7.582L4.919 1.263c-.137-.423-.733-.423-.868 0L1.387 9.452.045 13.587c-.121.374.016.786.335 1.018l11.62 8.442 11.62-8.442c.319-.232.456-.644.335-1.018z" />
                            </svg>
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-slate-800 text-sm truncate">
                            {repo.name}
                          </p>
                          <p className="text-xs text-slate-400 truncate">
                            {repo.full_name}
                          </p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-[10px] px-1.5 py-0.5 rounded-md font-bold uppercase tracking-wider bg-slate-100 text-slate-500 border border-slate-200">
                              {repo.visibility}
                            </span>
                          </div>
                        </div>
                      </div>
                      <button
                        onClick={() => startOnboarding(repo)}
                        disabled={connectedIds.has(repo.id)}
                        className="ml-4 px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
                      >
                        {connectedIds.has(repo.id) ? "Connected ✓" : "Connect"}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="p-6 border-t border-slate-100 flex items-center justify-end">
              <button
                onClick={handleClose}
                className="px-5 py-2.5 rounded-xl border border-slate-200 text-slate-600 text-sm font-semibold hover:bg-slate-50 transition-colors"
              >
                Cancel
              </button>
            </div>
          </>
        )}

        {/* Render Onboarding Credentials Step */}
        {step === "onboard" && selectedRepo && (
          <form
            onSubmit={handleOnboardSubmit}
            className="flex flex-col flex-1 overflow-hidden"
          >
            {/* Header */}
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <div>
                <span className="text-[10px] text-[#FC6D26] uppercase font-bold tracking-wider">
                  Step 2 of 2: Configuration
                </span>
                <h2 className="text-xl font-bold text-slate-950 mt-0.5">
                  Configure {selectedRepo.name}
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setStep("list")}
                className="px-3 py-1.5 bg-slate-50 hover:bg-slate-100 rounded-lg text-xs font-bold text-slate-500 hover:text-slate-800 transition-all flex items-center gap-1.5 border border-slate-200"
              >
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
                    d="M15 19l-7-7 7-7"
                  />
                </svg>
                Back
              </button>
            </div>

            {/* Onboarding Form Content */}
            <div className="flex-1 overflow-y-auto py-6 space-y-6">
              {/* Scan Banner / Status */}
              {isScanning ? (
                <div className="bg-slate-900 text-slate-100 rounded-2xl p-5 border border-slate-800 flex items-center gap-4 relative overflow-hidden animate-pulse shadow-md">
                  <div className="w-8 h-8 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin shrink-0"></div>
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-wider text-indigo-400">
                      Scanning repository...
                    </h4>
                    <p className="text-xs text-slate-300 mt-0.5">
                      Inspecting files (`.env`, config files) for database URIs
                      & secrets.
                    </p>
                  </div>
                </div>
              ) : scanResults ? (
                <div className="bg-slate-50 border border-slate-100 rounded-2xl p-4">
                  <div className="flex items-start gap-3">
                    {scanResults.error ? (
                      <>
                        <div className="w-8 h-8 rounded-full bg-amber-50 border border-amber-200 flex items-center justify-center shrink-0">
                          <svg
                            className="w-4 h-4 text-amber-500"
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
                        <div>
                          <h4 className="text-xs font-bold text-slate-800">
                            Scan Complete
                          </h4>
                          <p className="text-xs text-slate-500 mt-0.5">
                            {scanResults.error}
                          </p>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="w-8 h-8 rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center shrink-0">
                          <svg
                            className="w-4 h-4 text-emerald-600"
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
                        </div>
                        <div className="flex-1 min-w-0">
                          <h4 className="text-xs font-bold text-slate-800">
                            Scan Complete
                          </h4>
                          <p className="text-xs text-slate-500 mt-0.5">
                            {scanResults.mongodb_uri ||
                            scanResults.fivetran_api_key
                              ? `Detected connection secrets in: ${scanResults.detected_in_files.join(", ")}`
                              : "No configuration variables detected in the repository files. Ready for manual entry."}
                          </p>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              ) : null}

              {onboardingError && (
                <div className="bg-rose-50 border border-rose-100 rounded-2xl p-4 flex items-start gap-3">
                  <svg
                    className="w-5 h-5 text-rose-500 shrink-0 mt-0.5"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2.2"
                      d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                  <p className="text-xs font-semibold text-rose-700">
                    {onboardingError}
                  </p>
                </div>
              )}

              {/* Form Input Fields */}
              <div className="space-y-4">
                {/* MongoDB Connection URI */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-500">
                      MongoDB Connection URI
                    </label>
                    {scanResults?.mongodb_uri && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-100 font-bold">
                        Auto-detected
                      </span>
                    )}
                  </div>
                  <div className="relative">
                    <input
                      type={showMongodbUri ? "text" : "password"}
                      placeholder="mongodb+srv://username:password@cluster.mongodb.net/database"
                      className="w-full pl-4 pr-12 py-3 bg-slate-50/50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#FC6D26]/20 focus:border-[#FC6D26] text-sm text-slate-800 placeholder-slate-400 transition-all focus:bg-white font-mono"
                      value={mongodbUri}
                      onChange={(e) => setMongodbUri(e.target.value)}
                    />
                    <button
                      type="button"
                      onClick={() => setShowMongodbUri(!showMongodbUri)}
                      className="absolute right-3.5 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-slate-600 focus:outline-none transition-colors duration-200"
                      title={showMongodbUri ? "Hide URI" : "Show URI"}
                    >
                      {showMongodbUri ? (
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
                            d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"
                          />
                        </svg>
                      ) : (
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
                  <p className="text-[10px] text-slate-400 mt-1">
                    Connecting to your database enables Gatekeeper to inspect
                    schema designs, detect drifts, and recommend precise
                    remediations.
                  </p>
                </div>

                {/* Fivetran API Configuration */}
                <div className="pt-2 border-t border-slate-100">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3 flex items-center gap-1.5">
                    <svg
                      className="w-4 h-4 text-[#FC6D26]"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"
                      />
                    </svg>
                    Fivetran Connectors (Optional)
                  </h4>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wide">
                          Fivetran API Key
                        </label>
                        {scanResults?.fivetran_api_key && (
                          <span className="text-[8px] px-1 bg-emerald-50 text-emerald-700 rounded font-bold">
                            Auto-detected
                          </span>
                        )}
                      </div>
                      <input
                        type="text"
                        placeholder="API Key"
                        className="w-full px-4 py-2.5 bg-slate-50/50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#FC6D26]/20 focus:border-[#FC6D26] text-sm text-slate-800 placeholder-slate-400 transition-all focus:bg-white font-mono"
                        value={fivetranApiKey}
                        onChange={(e) => setFivetranApiKey(e.target.value)}
                      />
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wide">
                          Fivetran API Secret
                        </label>
                        {scanResults?.fivetran_api_secret && (
                          <span className="text-[8px] px-1 bg-emerald-50 text-emerald-700 rounded font-bold">
                            Auto-detected
                          </span>
                        )}
                      </div>
                      <div className="relative">
                        <input
                          type={showFivetranApiSecret ? "text" : "password"}
                          placeholder="API Secret"
                          className="w-full pl-4 pr-12 py-2.5 bg-slate-50/50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#FC6D26]/20 focus:border-[#FC6D26] text-sm text-slate-800 placeholder-slate-400 transition-all focus:bg-white font-mono"
                          value={fivetranApiSecret}
                          onChange={(e) => setFivetranApiSecret(e.target.value)}
                        />
                        <button
                          type="button"
                          onClick={() =>
                            setShowFivetranApiSecret(!showFivetranApiSecret)
                          }
                          className="absolute right-3.5 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-slate-600 focus:outline-none transition-colors duration-200"
                          title={
                            showFivetranApiSecret
                              ? "Hide Secret"
                              : "Show Secret"
                          }
                        >
                          {showFivetranApiSecret ? (
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
                                d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"
                              />
                            </svg>
                          ) : (
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
                </div>

                {/* Encryption Settings Checkbox */}
                <div className="p-4 bg-slate-50 border border-slate-100 rounded-2xl flex items-start gap-3 mt-4">
                  <input
                    type="checkbox"
                    id="encrypt-creds"
                    className="mt-1 h-4.5 w-4.5 text-[#FC6D26] focus:ring-[#FC6D26]/30 border-slate-300 rounded-md cursor-pointer accent-[#FC6D26]"
                    checked={encryptCredentials}
                    onChange={(e) => setEncryptCredentials(e.target.checked)}
                  />
                  <div className="cursor-pointer">
                    <label
                      htmlFor="encrypt-creds"
                      className="block text-xs font-bold text-slate-800 cursor-pointer select-none"
                    >
                      Encrypt Connection Credentials
                    </label>
                    <p className="text-[10px] text-slate-400 mt-0.5 leading-relaxed">
                      Recommended. Encrypts sensitive keys with a secure
                      symmetric cipher (AES) at rest.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="p-6 border-t border-slate-100 flex items-center justify-between bg-slate-50/30">
              <button
                type="button"
                onClick={() => setStep("list")}
                className="px-5 py-2.5 rounded-xl border border-slate-200 text-slate-600 text-sm font-semibold hover:bg-slate-50 transition-colors"
              >
                Back
              </button>

              <button
                type="submit"
                disabled={onboardMutation.isPending || isScanning}
                className="px-6 py-2.5 bg-[#FC6D26] hover:bg-[#E24329] text-white text-sm font-bold rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-md shadow-orange-500/10"
              >
                {onboardMutation.isPending ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    Onboarding...
                  </>
                ) : (
                  "Save & Onboard"
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default ConnectRepositoryModal;
