import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ApprovalCard } from "./ApprovalCard";

const approval = {
  reason: "Post review comment",
  tool_name: "post_gitlab_mr_comment",
  tool_args: { body: "LGTM" },
  risk_level: "mutating",
  estimated_scope: "1 comment",
  step_id: "s1",
};

describe("ApprovalCard", () => {
  it("renders approval details and handles approve/reject", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();

    render(
      <ApprovalCard
        pendingApproval={approval}
        onApprove={onApprove}
        onReject={onReject}
        onModify={vi.fn()}
      />,
    );

    expect(screen.getByText("post_gitlab_mr_comment")).toBeInTheDocument();
    expect(screen.getByText("Post review comment")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));

    expect(onApprove).toHaveBeenCalledTimes(1);
    expect(onReject).toHaveBeenCalledTimes(1);
  });
});
