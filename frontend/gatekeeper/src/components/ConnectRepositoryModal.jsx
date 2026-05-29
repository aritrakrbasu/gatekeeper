/**
 * ConnectRepositoryModal Component
 *
 * Modal for searching, scanning, and onboarding GitLab repositories.
 * Uses React Query for optimized caching, credential scanning, and secure onboarding.
 */

import React, { useState, useEffect } from "react";
import {
  useAvailableRepositories,
  useScanRepository,
  useOnboardRepository,
  useRepositoryBranches,
} from "../services/queries";
import { useDebounce } from "../hooks/useDebounce";

const ConnectRepositoryModal = ({ isOpen, onClose, onConnect }) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [connectedIds, setConnectedIds] = useState(new Set());

  // Onboarding workflow states
  const [step, setStep] = useState("list"); // "list" | "branches" | "config"
  const [selectedRepo, setSelectedRepo] = useState(null);
  const [mongodbUri, setMongodbUri] = useState("");
  const [fivetranApiKey, setFivetranApiKey] = useState("");
  const [fivetranApiSecret, setFivetranApiSecret] = useState("");
  const [encryptCredentials, setEncryptCredentials] = useState(true);
  const [showMongodbUri, setShowMongodbUri] = useState(false);
  const [showFivetranApiSecret, setShowFivetranApiSecret] = useState(false);

  // Branch selection state
  const [branches, setBranches] = useState([]);
  const [selectedBranches, setSelectedBranches] = useState([]);
  const [branchSearchQuery, setBranchSearchQuery] = useState("");
  const [isLoadingBranches, setIsLoadingBranches] = useState(false);
  const [branchesError, setBranchesError] = useState(null);

  const [isScanning, setIsScanning] = useState(false);
  const [scanResults, setScanResults] = useState(null);
  const [onboardingError, setOnboardingError] = useState(null);

  // Debounce the search query to reduce API calls (500ms delay)
  const debouncedSearchQuery = useDebounce(searchQuery, 500);

  // Debounce branch search query
  const debouncedBranchSearchQuery = useDebounce(branchSearchQuery, 200);

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

  // Fetch branches when a repo is selected
  const { data: branchesData } = useRepositoryBranches(
    selectedRepo?.id,
    isOpen && (step === "branches" || step === "config") && !!selectedRepo,
  );

  // Update branches when data is fetched
  useEffect(() => {
    if (branchesData && branchesData.branches) {
      setBranches(branchesData.branches);
      // Auto-select default and protected branches
      const defaultBranches = branchesData.branches
        .filter(
          (b) =>
            b.default ||
            b.protected ||
            b.name === "main" ||
            b.name === "master" ||
            b.name === "develop",
        )
        .map((b) => b.name);
      setSelectedBranches(
        defaultBranches.length > 0 ? defaultBranches : ["main"],
      );
    }
  }, [branchesData]);

  // Mutations for scanning and onboarding
  const scanMutation = useScanRepository();
  const onboardMutation = useOnboardRepository();

  // Reset states on close
  const handleClose = () => {
    setStep("list");
    setSelectedRepo(null);
    setSearchQuery("");
    setMongodbUri("");
    setFivetranApiKey("");
    setFivetranApiSecret("");
    setEncryptCredentials(true);
    setBranches([]);
    setSelectedBranches([]);
    setBranchSearchQuery("");
    setIsLoadingBranches(false);
    setBranchesError(null);
    setScanResults(null);
    setIsScanning(false);
    setOnboardingError(null);
    setShowMongodbUri(false);
    setShowFivetranApiSecret(false);
    onClose();
  };

  // Start onboarding: change step to branch selection
  const startOnboarding = async (repo) => {
    setSelectedRepo(repo);
    setStep("branches");
    setBranches([]);
    setSelectedBranches([]);
    setBranchSearchQuery("");
    setBranchesError(null);
    setScanResults(null);
    setOnboardingError(null);
    setMongodbUri("");
    setFivetranApiKey("");
    setFivetranApiSecret("");
    setIsScanning(false);
  };

  // Move from branch selection to config step
  const moveToConfig = async () => {
    setStep("config");
    setIsScanning(true);
    setScanResults(null);
    setOnboardingError(null);

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
  };

  // Toggle branch selection
  const toggleBranch = (branchName) => {
    setSelectedBranches((prev) =>
      prev.includes(branchName)
        ? prev.filter((b) => b !== branchName)
        : [...prev, branchName],
    );
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
          branches: selectedBranches,
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

  // Filter branches based on search query
  const filteredBranches = branches.filter((branch) =>
    branch.name
      .toLowerCase()
      .includes(debouncedBranchSearchQuery.toLowerCase()),
  );

  // Get step info
  const getStepInfo = () => {
    switch (step) {
      case "list":
        return { number: 1, title: "Select Repository" };
      case "branches":
        return { number: 2, title: "Select Branches" };
      case "config":
        return { number: 3, title: "Configuration" };
      default:
        return { number: 1, title: "Select Repository" };
    }
  };

  const stepInfo = getStepInfo();

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
                  <span className="text-[10px] text-[#FC6D26] uppercase font-bold tracking-wider">
                    Step 1 of 3: Select Repository
                  </span>
                  <h2 className="text-xl font-bold text-slate-950 mt-0.5">
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

        {/* Render Branch Selection Step */}
        {step === "branches" && selectedRepo && (
          <div className="flex flex-col flex-1 overflow-hidden">
            {/* Header */}
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <div>
                <span className="text-[10px] text-[#FC6D26] uppercase font-bold tracking-wider">
                  Step 2 of 3: Select Branches
                </span>
                <h2 className="text-xl font-bold text-slate-950 mt-0.5">
                  {selectedRepo.name}
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Select branches to monitor for merge requests
                </p>
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

            {/* Branch Selection Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              <div>
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
                      d="M13 10V3L4 14h7v7l9-11h-7z"
                    />
                  </svg>
                  Webhook Branch Selection
                </h4>

                <p className="text-xs text-slate-500 mb-3">
                  Select which branches should trigger Gatekeeper's MR review
                  when merge requests are opened.
                </p>

                {/* Branch Search */}
                <div className="relative mb-3">
                  <svg
                    className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 transform -translate-y-1/2"
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
                    placeholder="Search branches..."
                    className="w-full pl-10 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#FC6D26]/20 focus:border-[#FC6D26] text-sm text-slate-800 placeholder-slate-400 transition-all focus:bg-white"
                    value={branchSearchQuery}
                    onChange={(e) => setBranchSearchQuery(e.target.value)}
                  />
                  {branchSearchQuery && (
                    <button
                      type="button"
                      onClick={() => setBranchSearchQuery("")}
                      className="absolute right-3 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-slate-600"
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
                  )}
                </div>

                {filteredBranches.length === 0 && branches.length === 0 ? (
                  <div className="text-center py-8 bg-slate-50 rounded-xl">
                    <div className="w-8 h-8 bg-slate-200 rounded-full flex items-center justify-center mx-auto mb-2">
                      <svg
                        className="w-4 h-4 text-slate-400 animate-spin"
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
                    </div>
                    <p className="text-xs text-slate-400">
                      Loading branches...
                    </p>
                  </div>
                ) : filteredBranches.length === 0 ? (
                  <div className="text-center py-8 bg-slate-50 rounded-xl">
                    <div className="w-8 h-8 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-2">
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
                          d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                        />
                      </svg>
                    </div>
                    <p className="text-xs text-slate-500">
                      No branches match "{branchSearchQuery}"
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {filteredBranches.map((branch) => (
                      <label
                        key={branch.name}
                        className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                          selectedBranches.includes(branch.name)
                            ? "bg-[#FC6D26]/10 border-[#FC6D26] hover:bg-[#FC6D26]/15"
                            : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={selectedBranches.includes(branch.name)}
                          onChange={() => toggleBranch(branch.name)}
                          className="w-4 h-4 text-[#FC6D26] focus:ring-[#FC6D26]/30 border-slate-300 rounded cursor-pointer"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-slate-800 truncate">
                              {branch.name}
                            </span>
                            {branch.default && (
                              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 font-bold">
                                Default
                              </span>
                            )}
                            {branch.protected && (
                              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 font-bold">
                                Protected
                              </span>
                            )}
                          </div>
                        </div>
                      </label>
                    ))}
                  </div>
                )}

                {selectedBranches.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    <span className="text-xs text-slate-500 py-1">
                      Selected:
                    </span>
                    {selectedBranches.map((branch) => (
                      <span
                        key={branch}
                        className="text-xs px-2 py-1 rounded-lg bg-[#FC6D26]/10 text-[#FC6D26] font-medium flex items-center gap-1"
                      >
                        {branch}
                        <button
                          type="button"
                          onClick={() => toggleBranch(branch)}
                          className="hover:text-[#E24329]"
                        >
                          <svg
                            className="w-3 h-3"
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
                      </span>
                    ))}
                  </div>
                )}
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
                type="button"
                onClick={moveToConfig}
                disabled={selectedBranches.length === 0}
                className="px-6 py-2.5 bg-[#FC6D26] hover:bg-[#E24329] text-white text-sm font-bold rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-md shadow-orange-500/10"
              >
                Next
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
                    d="M9 5l7 7-7 7"
                  />
                </svg>
              </button>
            </div>
          </div>
        )}

        {/* Render Configuration Step */}
        {step === "config" && selectedRepo && (
          <form
            onSubmit={handleOnboardSubmit}
            className="flex flex-col flex-1 overflow-hidden"
          >
            {/* Header */}
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <div>
                <span className="text-[10px] text-[#FC6D26] uppercase font-bold tracking-wider">
                  Step 3 of 3: Configuration
                </span>
                <h2 className="text-xl font-bold text-slate-950 mt-0.5">
                  Configure {selectedRepo.name}
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setStep("branches")}
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
            <div className="flex-1 overflow-y-auto px-6 space-y-6">
              {/* Selected Branches Summary */}
              <div className="bg-slate-50 border border-slate-100 rounded-2xl p-4">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-full bg-[#FC6D26]/10 border border-[#FC6D26]/20 flex items-center justify-center shrink-0">
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
                        d="M13 10V3L4 14h7v7l9-11h-7z"
                      />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <h4 className="text-xs font-bold text-slate-800">
                      Monitoring Branches
                    </h4>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Gatekeeper will review MRs targeting:{" "}
                      <span className="font-medium text-slate-700">
                        {selectedBranches.length > 0
                          ? selectedBranches.join(", ")
                          : "none"}
                      </span>
                    </p>
                  </div>
                </div>
              </div>

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
                onClick={() => setStep("branches")}
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
