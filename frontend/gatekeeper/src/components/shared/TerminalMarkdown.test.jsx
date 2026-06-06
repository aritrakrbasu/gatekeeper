import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { TerminalMarkdown } from "./TerminalMarkdown";

describe("TerminalMarkdown", () => {
  it("renders markdown headings with terminal styling", () => {
    render(<TerminalMarkdown>{"# Title\n\nParagraph text."}</TerminalMarkdown>);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toHaveClass("text-lg", "font-bold", "text-white");
    expect(screen.getByText("Paragraph text.")).toHaveClass("text-slate-300");
  });

  it("styles links with brand color", () => {
    render(
      <TerminalMarkdown>{"[Gatekeeper](https://example.com)"}</TerminalMarkdown>,
    );
    const link = screen.getByRole("link", { name: "Gatekeeper" });
    expect(link).toHaveAttribute("href", "https://example.com");
    expect(link).toHaveClass("text-[#FC6D26]");
  });

  it("does not render raw HTML (ReactMarkdown default security)", () => {
    render(
      <TerminalMarkdown>{"<script>alert('xss')</script>"}</TerminalMarkdown>,
    );
    expect(screen.queryByText("alert('xss')")).not.toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });

  it("renders inline and block code with distinct classes", () => {
    const { container } = render(
      <TerminalMarkdown>{"`inline` and\n\n```\nblock\n```"}</TerminalMarkdown>,
    );
    const codes = container.querySelectorAll("code");
    expect(codes.length).toBeGreaterThanOrEqual(2);
    expect(codes[0]).toHaveClass("text-emerald-400");
  });
});
