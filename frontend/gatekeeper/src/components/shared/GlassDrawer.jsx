import React from "react";

/**
 * Right-side drawer shell for Copilot and other slide-over panels.
 * Desktop: 480px width. Mobile: full-screen sheet.
 */
export function GlassDrawer({
  isOpen,
  onClose,
  children,
  zIndex = "z-[100]",
  backdropClass = "bg-slate-900/40",
}) {
  if (!isOpen) return null;

  return (
    <div className={`fixed inset-0 ${zIndex}`}>
      <div
        className={`absolute inset-0 ${backdropClass} backdrop-blur-sm transition-opacity`}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        className="absolute inset-y-0 right-0 w-full md:w-[480px] bg-white/95 backdrop-blur-2xl border-l border-white shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-200"
      >
        {children}
      </div>
    </div>
  );
}
