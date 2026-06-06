import React from "react";

export function UserMessage({ content }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] bg-white border border-slate-100 rounded-2xl px-4 py-2 text-sm text-slate-800 shadow-sm">
        <p className="whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  );
}
