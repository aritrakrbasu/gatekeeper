import { describe, it, expect } from "vitest";
import { getPlanStepStatus, PLAN_STEP_STATUS } from "./planStepStatus";

describe("getPlanStepStatus", () => {
  it("marks steps before cursor as completed", () => {
    expect(getPlanStepStatus(0, 2)).toBe(PLAN_STEP_STATUS.COMPLETED);
  });

  it("marks cursor step as running when streaming", () => {
    expect(getPlanStepStatus(2, 2, { isStreaming: true })).toBe(
      PLAN_STEP_STATUS.RUNNING,
    );
  });

  it("marks steps after cursor as pending", () => {
    expect(getPlanStepStatus(3, 2)).toBe(PLAN_STEP_STATUS.PENDING);
  });
});
