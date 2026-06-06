import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { GlassDrawer } from "./GlassDrawer";

describe("GlassDrawer", () => {
  it("returns null when closed", () => {
    const { container } = render(
      <GlassDrawer isOpen={false} onClose={() => {}}>
        <p>Drawer</p>
      </GlassDrawer>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders children when open", () => {
    render(
      <GlassDrawer isOpen onClose={() => {}}>
        <p>Drawer content</p>
      </GlassDrawer>,
    );
    expect(screen.getByText("Drawer content")).toBeInTheDocument();
  });

  it("uses full width on mobile and 480px on desktop", () => {
    render(
      <GlassDrawer isOpen onClose={() => {}}>
        <p>Panel</p>
      </GlassDrawer>,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveClass("w-full");
    expect(dialog).toHaveClass("md:w-[480px]");
  });

  it("calls onClose when backdrop is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(
      <GlassDrawer isOpen onClose={onClose}>
        <p>Panel</p>
      </GlassDrawer>,
    );
    const backdrop = container.querySelector('[aria-hidden="true"]');
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
