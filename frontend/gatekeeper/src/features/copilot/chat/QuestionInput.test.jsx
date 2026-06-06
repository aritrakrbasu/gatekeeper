import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QuestionInput } from "./QuestionInput";

describe("QuestionInput", () => {
  it("submits on Enter without Shift", () => {
    const onSubmit = vi.fn();
    render(<QuestionInput onSubmit={onSubmit} />);

    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "Why was this rejected?" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });

    expect(onSubmit).toHaveBeenCalledWith("Why was this rejected?");
  });

  it("does not submit on Shift+Enter", () => {
    const onSubmit = vi.fn();
    render(<QuestionInput onSubmit={onSubmit} />);

    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "Line one" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables input when disabled prop is true", () => {
    render(<QuestionInput onSubmit={() => {}} disabled />);
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});
