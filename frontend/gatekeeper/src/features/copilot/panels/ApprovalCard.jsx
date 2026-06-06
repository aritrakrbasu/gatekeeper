import React, { useState } from "react";

export function ApprovalCard({ pendingApproval, onApprove, onReject, onModify }) {
  const [showModify, setShowModify] = useState(false);
  const [modifiedArgs, setModifiedArgs] = useState(
    JSON.stringify(pendingApproval?.tool_args ?? {}, null, 2),
  );

  if (!pendingApproval) {
    return null;
  }

  const handleModify = () => {
    try {
      const parsed = JSON.parse(modifiedArgs);
      onModify(parsed);
      setShowModify(false);
    } catch {
      // Keep editor open on invalid JSON
    }
  };

  return (
    <div className="mx-4 mb-3 rounded-2xl border border-amber-300 bg-amber-50 p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-2">
        <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
        <h3 className="text-sm font-bold text-amber-900">Approval Required</h3>
      </div>

      <dl className="space-y-1 text-xs text-amber-900/90 mb-3">
        <div>
          <dt className="font-semibold inline">Tool: </dt>
          <dd className="inline font-mono">{pendingApproval.tool_name}</dd>
        </div>
        <div>
          <dt className="font-semibold inline">Risk: </dt>
          <dd className="inline uppercase">{pendingApproval.risk_level}</dd>
        </div>
        <div>
          <dt className="font-semibold inline">Scope: </dt>
          <dd className="inline">{pendingApproval.estimated_scope}</dd>
        </div>
        <div>
          <dt className="font-semibold">Reason</dt>
          <dd>{pendingApproval.reason}</dd>
        </div>
      </dl>

      {showModify && (
        <textarea
          value={modifiedArgs}
          onChange={(event) => setModifiedArgs(event.target.value)}
          rows={4}
          className="w-full mb-3 rounded-lg border border-amber-200 bg-white px-2 py-1 font-mono text-xs"
        />
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onApprove}
          className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg"
        >
          Approve
        </button>
        <button
          type="button"
          onClick={onReject}
          className="bg-rose-600 hover:bg-rose-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg"
        >
          Reject
        </button>
        <button
          type="button"
          onClick={() => (showModify ? handleModify() : setShowModify(true))}
          className="bg-white hover:bg-amber-100 border border-amber-300 text-amber-900 text-xs font-medium px-3 py-1.5 rounded-lg"
        >
          {showModify ? "Submit Modified" : "Modify"}
        </button>
      </div>
    </div>
  );
}
