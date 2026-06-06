import React, { useState } from "react";

export function QuestionInput({ onSubmit, disabled = false, placeholder }) {
  const [value, setValue] = useState("");

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) {
      return;
    }
    onSubmit(trimmed);
    setValue("");
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t border-slate-100 bg-white/80 p-4">
      <div className="flex gap-2 items-end">
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={2}
          placeholder={
            placeholder ?? "Ask about this review... (Enter to send, Shift+Enter for newline)"
          }
          className="flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#FC6D26]/30 focus:border-[#FC6D26] disabled:opacity-50 disabled:cursor-not-allowed"
        />
        <button
          type="button"
          onClick={handleSubmit}
          disabled={disabled || !value.trim()}
          className="shrink-0 bg-[#FC6D26] hover:bg-[#E24329] disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2 px-4 rounded-xl transition-colors text-sm"
        >
          Send
        </button>
      </div>
    </div>
  );
}
