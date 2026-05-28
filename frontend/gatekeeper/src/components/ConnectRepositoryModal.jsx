/**
 * ConnectRepositoryModal Component
 *
 * Modal for searching and connecting GitLab repositories.
 * Now using React Query for optimized caching and data fetching.
 */

import React, { useState, useEffect } from "react";
import { useAvailableRepositories, useConnectRepository } from "../services/queries";
import { useDebounce } from "../hooks/useDebounce";

const ConnectRepositoryModal = ({ isOpen, onClose, onConnect }) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [connectedIds, setConnectedIds] = useState(new Set());

  // Debounce the search query to reduce API calls (500ms delay)
  const debouncedSearchQuery = useDebounce(searchQuery, 500);

  // Use React Query hook for fetching available repositories with caching
  const { data: repositories = [], isLoading, error, refetch } = useAvailableRepositories(
    debouncedSearchQuery,
    isOpen // Only fetch when modal is open
  );

  // Use React Query mutation for connecting repositories
  const connectMutation = useConnectRepository();

  // Handle connect with loading state
  const handleConnect = async (repo) => {
    try {
      await connectMutation.mutateAsync(repo.id);
      setConnectedIds(new Set([...connectedIds, repo.id]));
      onConnect && onConnect(repo);
    } catch (err) {
      console.error("Failed to connect repository:", err);
      alert(err.message || "Failed to connect repository");
    }
  };

  const handleConnectAndClose = async (repo) => {
    await handleConnect(repo);
    // Refresh the list to remove connected repo (React Query handles this automatically)
    await refetch();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-slate-200">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-slate-900">
              Connect Repository
            </h2>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 flex items-center justify-center transition-colors"
            >
              <svg className="w-5 h-5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Search */}
          <div className="relative">
            <svg
              className="w-5 h-5 text-slate-400 absolute left-3 top-1/2 transform -translate-y-1/2"
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
              className="w-full pl-11 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#FC6D26]/50 focus:border-[#FC6D26] transition-all"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {isLoading && repositories.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#FC6D26]"></div>
            </div>
          ) : error ? (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
              <div className="flex items-center gap-3">
                <svg className="w-5 h-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p className="text-sm text-red-700">{error}</p>
              </div>
            </div>
          ) : repositories.length === 0 ? (
            <div className="text-center py-12">
              <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-slate-900 mb-2">
                {debouncedSearchQuery ? "No repositories found" : "All repositories connected"}
              </h3>
              <p className="text-slate-500 text-sm">
                {debouncedSearchQuery
                  ? "Try a different search term"
                  : "You've connected all your GitLab repositories"}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {repositories.map((repo) => (
                <div
                  key={repo.id}
                  className="flex items-center justify-between p-4 bg-slate-50 rounded-xl hover:bg-slate-100 transition-colors group"
                >
                  <div className="flex items-center gap-4 flex-1 min-w-0">
                    {repo.avatar_url ? (
                      <img
                        src={repo.avatar_url}
                        alt={repo.name}
                        className="w-12 h-12 rounded-xl object-cover"
                      />
                    ) : (
                      <div className="w-12 h-12 rounded-xl bg-white border border-slate-200 flex items-center justify-center">
                        <svg className="w-6 h-6 text-[#FC6D26]" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M23.955 13.587l-1.342-4.135-2.664-8.189c-.135-.423-.73-.423-.867 0L16.418 9.45H7.582L4.919 1.263c-.137-.423-.733-.423-.868 0L1.387 9.452.045 13.587c-.121.374.016.786.335 1.018l11.62 8.442 11.62-8.442c.319-.232.456-.644.335-1.018z" />
                        </svg>
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-slate-900 truncate">
                        {repo.name}
                      </p>
                      <p className="text-sm text-slate-500 truncate">
                        {repo.full_name}
                      </p>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-xs px-2 py-0.5 rounded-full bg-slate-200 text-slate-600">
                          {repo.visibility}
                        </span>
                        {repo.star_count > 0 && (
                          <span className="text-xs text-slate-400 flex items-center gap-1">
                            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                              <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                            </svg>
                            {repo.star_count}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => handleConnectAndClose(repo)}
                    disabled={connectMutation.isPending || connectedIds.has(repo.id)}
                    className="ml-4 px-4 py-2 bg-[#FC6D26] hover:bg-[#E24329] text-white text-sm font-medium rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shrink-0"
                  >
                    {connectMutation.isPending ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                        Connecting...
                      </>
                    ) : connectedIds.has(repo.id) ? (
                      "Connected ✓"
                    ) : (
                      "Connect"
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-slate-200">
          <button
            onClick={onClose}
            className="w-full py-3 rounded-xl border border-slate-300 text-slate-700 font-medium hover:bg-slate-50 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConnectRepositoryModal;
