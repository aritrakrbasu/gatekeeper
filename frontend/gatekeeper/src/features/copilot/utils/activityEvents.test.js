import { describe, it, expect } from "vitest";
import { STREAM_EVENTS } from "../constants/streamEvents";
import { mapActivityEventsToLogs } from "./activityEvents";

describe("mapActivityEventsToLogs", () => {
  it("maps node and approval events to activity log entries", () => {
    const logs = mapActivityEventsToLogs([
      {
        type: STREAM_EVENTS.NODE_STARTED,
        node: "planner",
        timestamp: "2026-06-06T12:00:00Z",
      },
      {
        type: STREAM_EVENTS.APPROVAL_REQUIRED,
        data: { tool_name: "post_gitlab_mr_comment" },
        timestamp: "2026-06-06T12:00:05Z",
      },
    ]);

    expect(logs[0].message).toContain("Started planner");
    expect(logs[0].status).toBe("running");
    expect(logs[1].message).toContain("post_gitlab_mr_comment");
  });
});
