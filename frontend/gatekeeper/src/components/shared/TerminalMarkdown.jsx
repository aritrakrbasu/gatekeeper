import React from "react";
import ReactMarkdown from "react-markdown";

/**
 * ReactMarkdown component map for terminal-style dark prose.
 * Extracted from RepoDetails AI summary rendering.
 */
export const terminalMarkdownComponents = {
  h1: ({ node, ...props }) => (
    <h1 className="text-lg font-bold text-white mb-3" {...props} />
  ),
  h2: ({ node, ...props }) => (
    <h2 className="text-base font-bold text-white mb-2 mt-4" {...props} />
  ),
  h3: ({ node, ...props }) => (
    <h3 className="text-sm font-bold text-white mb-2 mt-3" {...props} />
  ),
  p: ({ node, ...props }) => (
    <p className="mb-2 text-slate-300" {...props} />
  ),
  ul: ({ node, ...props }) => (
    <ul className="list-disc list-inside mb-3 text-slate-300" {...props} />
  ),
  ol: ({ node, ...props }) => (
    <ol className="list-decimal list-inside mb-3 text-slate-300" {...props} />
  ),
  li: ({ node, ...props }) => <li className="mb-1" {...props} />,
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
      <table className="min-w-full divide-y divide-slate-700" {...props} />
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
};

/**
 * Renders markdown with terminal-style dark prose styling.
 * Uses ReactMarkdown default security (no raw HTML rendering).
 */
export function TerminalMarkdown({ children, className }) {
  const proseClass =
    className ??
    "text-slate-300 text-sm leading-relaxed relative z-10 prose prose-invert prose-sm max-w-none";

  return (
    <div className={proseClass}>
      <ReactMarkdown components={terminalMarkdownComponents}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
