/**
 * BranchSelector Component
 *
 * Displays a list of GitLab branches with checkboxes for selection.
 * Features search/filter, select all/deselect all, and highlights the default branch.
 */

import React, { useState, useMemo } from "react";

const BranchSelector = ({
  branches = [],
  selectedBranches = [],
  onToggleBranch,
  defaultBranch,
  isLoading = false
}) => {
  const [searchQuery, setSearchQuery] = useState("");

  // Filter branches based on search query
  const filteredBranches = useMemo(() => {
    if (!searchQuery) return branches;

    const query = searchQuery.toLowerCase();
    return branches.filter(branch =>
      branch.name.toLowerCase().includes(query) ||
      (branch.commit_title && branch.commit_title.toLowerCase().includes(query))
    );
  }, [branches, searchQuery]);

  // Toggle all branches
  const toggleAll = () => {
    const allSelected = filteredBranches.every(branch =>
      selectedBranches.includes(branch.name)
    );

    if (allSelected) {
      // Deselect all filtered branches
      filteredBranches.forEach(branch => {
        if (selectedBranches.includes(branch.name)) {
          onToggleBranch(branch.name);
        }
      });
    } else {
      // Select all filtered branches
      filteredBranches.forEach(branch => {
        if (!selectedBranches.includes(branch.name)) {
          onToggleBranch(branch.name);
        }
      });
    }
  };

  const allFilteredSelected = filteredBranches.length > 0 &&
    filteredBranches.every(branch => selectedBranches.includes(branch.name));

  const someFilteredSelected = filteredBranches.some(branch =>
    selectedBranches.includes(branch.name)
  );

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-[#FC6D26] border-t-transparent mb-3"></div>
        <p className="text-xs text-slate-400">Loading branches...</p>
      </div>
    );
  }

  if (branches.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="w-12 h-12 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-3">
          <svg className="w-6 h-6 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <h3 className="text-sm font-semibold text-slate-800 mb-1">No branches found</h3>
        <p className="text-xs text-slate-400">This repository has no branches to display</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {/* Search and Controls */}
      <div className="flex items-center gap-3 mb-4">
        {/* Search Input */}
        <div className="relative flex-1">
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
            className="w-full pl-10 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#FC6D26]/20 focus:border-[#FC6D26] text-sm text-slate-800 placeholder-slate-400 transition-all"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {/* Toggle All Button */}
        {filteredBranches.length > 1 && (
          <button
            type="button"
            onClick={toggleAll}
            className="px-4 py-2 text-xs font-semibold rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors whitespace-nowrap"
          >
            {allFilteredSelected ? "Deselect All" : "Select All"}
          </button>
        )}
      </div>

      {/* Branch Count */}
      <div className="text-xs text-slate-500 mb-3">
        {filteredBranches.length} {filteredBranches.length === 1 ? 'branch' : 'branches'} found
        {searchQuery && ` (filtered from ${branches.length})`}
      </div>

      {/* Branch List */}
      <div className="flex-1 overflow-y-auto max-h-80 space-y-2 pr-1">
        {filteredBranches.map((branch) => {
          const isSelected = selectedBranches.includes(branch.name);
          const isDefault = branch.name === defaultBranch;

          return (
            <div
              key={branch.name}
              className={`flex items-start gap-3 p-3 rounded-xl border transition-all cursor-pointer hover:shadow-sm ${
                isSelected
                  ? "bg-[#FC6D26]/5 border-[#FC6D26]/20"
                  : "bg-white border-slate-100 hover:border-slate-200"
              }`}
              onClick={() => onToggleBranch(branch.name)}
            >
              {/* Checkbox */}
              <div className="flex items-center justify-center pt-0.5">
                <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${
                  isSelected
                    ? "bg-[#FC6D26] border-[#FC6D26]"
                    : "border-slate-300 hover:border-slate-400"
                }`}>
                  {isSelected && (
                    <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </div>
              </div>

              {/* Branch Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`font-medium text-sm truncate ${
                    isSelected ? "text-slate-900" : "text-slate-700"
                  }`}>
                    {branch.name}
                  </span>
                  {isDefault && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500 border border-slate-200 font-bold uppercase tracking-wide">
                      Default
                    </span>
                  )}
                  {branch.protected && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-600 border border-amber-200 font-bold uppercase tracking-wide">
                      Protected
                    </span>
                  )}
                </div>
                {branch.commit_title && (
                  <p className="text-xs text-slate-400 truncate mt-0.5" title={branch.commit_title}>
                    {branch.commit_title}
                  </p>
                )}
              </div>

              {/* Commit ID */}
              {branch.short_id && (
                <div className="text-xs text-slate-400 font-mono shrink-0">
                  {branch.short_id}
                </div>
              )}
            </div>
          );
        })}

        {filteredBranches.length === 0 && searchQuery && (
          <div className="text-center py-8">
            <p className="text-sm text-slate-400">No branches match "{searchQuery}"</p>
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="mt-2 text-xs text-[#FC6D26] hover:underline"
            >
              Clear search
            </button>
          </div>
        )}
      </div>

      {/* Selection Summary */}
      {selectedBranches.length > 0 && (
        <div className="mt-4 pt-3 border-t border-slate-100">
          <p className="text-xs text-slate-500">
            <span className="font-semibold text-slate-700">{selectedBranches.length}</span> branch{selectedBranches.length !== 1 ? 'es' : ''} selected
          </p>
        </div>
      )}
    </div>
  );
};

export default BranchSelector;
