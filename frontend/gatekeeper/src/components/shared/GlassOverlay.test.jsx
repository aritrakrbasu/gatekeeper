import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { GlassOverlay } from "./GlassOverlay";

describe("GlassOverlay", () => {
  it("renders children when open", () => {
    render(
      <GlassOverlay>
        <p>Modal content</p>
      </GlassOverlay>,
    );
    expect(screen.getByText("Modal content")).toBeInTheDocument();
  });

  it("returns null when isOpen is false", () => {
    const { container } = render(
      <GlassOverlay isOpen={false}>
        <p>Hidden</p>
      </GlassOverlay>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("calls onClose when split-variant backdrop is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(
      <GlassOverlay onClose={onClose} variant="split">
        <p>Content</p>
      </GlassOverlay>,
    );
    const backdrop = container.querySelector('[aria-hidden="true"]');
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("applies split-variant panel classes from RepoDetails MR modal", () => {
    const { container } = render(
      <GlassOverlay
        variant="split"
        maxWidth="max-w-3xl"
        rounded="rounded-[2rem]"
        maxHeight="max-h-[90vh]"
        panelClassName="flex flex-col"
      >
        <p>MR modal</p>
      </GlassOverlay>,
    );
    const panel = screen.getByText("MR modal").parentElement;
    expect(panel).toHaveClass("max-w-3xl");
    expect(panel).toHaveClass("rounded-[2rem]");
    expect(panel).toHaveClass("max-h-[90vh]");
    expect(panel).toHaveClass("flex", "flex-col");
    expect(container.firstChild).toHaveClass("z-[100]");
  });

  it("applies unified-variant classes from ConnectRepositoryModal", () => {
    const { container } = render(
      <GlassOverlay
        variant="unified"
        zIndex="z-50"
        maxWidth="max-w-2xl"
        maxHeight="max-h-[85vh]"
        backdropClass="bg-slate-900/60"
        panelClassName="flex flex-col overflow-hidden"
      >
        <p>Connect repo</p>
      </GlassOverlay>,
    );
    expect(container.firstChild).toHaveClass("z-50");
    expect(container.firstChild).toHaveClass("bg-slate-900/60");
    const panel = screen.getByText("Connect repo").parentElement;
    expect(panel).toHaveClass("max-w-2xl");
    expect(panel).toHaveClass("max-h-[85vh]");
  });
});
