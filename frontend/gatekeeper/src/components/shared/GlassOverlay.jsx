import React from "react";

/**
 * Centered glassmorphism modal overlay.
 *
 * Variants:
 * - split (RepoDetails): separate backdrop layer with click-to-close
 * - unified (ConnectRepositoryModal): backdrop styles on the root element
 */
export function GlassOverlay({
  isOpen = true,
  onClose,
  children,
  variant = "split",
  zIndex = "z-[100]",
  maxWidth = "max-w-3xl",
  rounded = "rounded-[2rem]",
  maxHeight,
  panelClassName = "",
  backdropClass = "bg-slate-900/40",
  padding = "p-4 sm:p-6",
}) {
  if (!isOpen) return null;

  const panelClasses = [
    variant === "split" ? "relative w-full" : "w-full",
    maxWidth,
    variant === "split"
      ? "bg-white/95 backdrop-blur-2xl border border-white"
      : "bg-white border border-slate-100",
    rounded,
    "shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200",
    maxHeight,
    panelClassName,
  ]
    .filter(Boolean)
    .join(" ");

  if (variant === "unified") {
    return (
      <div
        className={`fixed inset-0 ${backdropClass} backdrop-blur-sm ${zIndex} flex items-center justify-center p-4 transition-all duration-300`}
      >
        <div className={panelClasses}>{children}</div>
      </div>
    );
  }

  return (
    <div
      className={`fixed inset-0 ${zIndex} flex items-center justify-center ${padding}`}
    >
      <div
        className={`absolute inset-0 ${backdropClass} backdrop-blur-sm transition-opacity`}
        onClick={onClose}
        aria-hidden="true"
      />
      <div className={panelClasses}>{children}</div>
    </div>
  );
}
