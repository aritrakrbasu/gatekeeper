import { describe, it, expect } from "vitest";
import { STREAM_EVENTS } from "../constants/streamEvents";
import {
  applyStreamEvent,
  hydrateMessagesFromBootstrap,
  pickConversationForSession,
  pickResumableConversation,
} from "./applyStreamEvent";

const baseState = {
  messages: [
    { id: "assistant-1", role: "assistant", content: "Hello", streaming: true },
  ],
  activityEvents: [],
  knowledgeManifest: {},
  streamingMessageId: "assistant-1",
};

describe("hydrateMessagesFromBootstrap", () => {
  it("maps checkpoint question and response to messages", () => {
    const messages = hydrateMessagesFromBootstrap({
      conversation: {
        last_question: "Why?",
        response_text: "Because.",
      },
    });

    expect(messages).toEqual([
      { id: "bootstrap-user", role: "user", content: "Why?" },
      { id: "bootstrap-assistant", role: "assistant", content: "Because." },
    ]);
  });
});

describe("pickConversationForSession", () => {
  it("prefers active conversations over completed ones", () => {
    const picked = pickConversationForSession([
      {
        conversation_id: "done",
        status: "completed",
        last_updated: "2026-06-06T13:00:00Z",
      },
      {
        conversation_id: "running",
        status: "running",
        last_updated: "2026-06-06T10:00:00Z",
      },
    ]);

    expect(picked.conversation_id).toBe("running");
  });

  it("falls back to the newest conversation when none are active", () => {
    const picked = pickConversationForSession([
      {
        conversation_id: "older",
        status: "completed",
        last_updated: "2026-06-06T10:00:00Z",
      },
      {
        conversation_id: "newer",
        status: "completed",
        last_updated: "2026-06-06T12:00:00Z",
      },
    ]);

    expect(picked.conversation_id).toBe("newer");
  });
});

describe("pickResumableConversation", () => {
  it("returns the newest running or waiting_approval conversation", () => {
    const picked = pickResumableConversation([
      {
        conversation_id: "old",
        status: "running",
        last_updated: "2026-06-06T10:00:00Z",
      },
      {
        conversation_id: "new",
        status: "waiting_approval",
        last_updated: "2026-06-06T12:00:00Z",
      },
      {
        conversation_id: "done",
        status: "completed",
        last_updated: "2026-06-06T13:00:00Z",
      },
    ]);

    expect(picked.conversation_id).toBe("new");
  });
});

describe("applyStreamEvent", () => {
  it("appends response chunks to the streaming assistant message", () => {
    const updates = applyStreamEvent(baseState, {
      event: STREAM_EVENTS.RESPONSE_CHUNK,
      data: { text: " world" },
    });

    expect(updates.messages[0].content).toBe("Hello world");
    expect(updates.messages[0].streaming).toBe(true);
  });

  it("records node lifecycle events in activityEvents", () => {
    const updates = applyStreamEvent(baseState, {
      event: STREAM_EVENTS.NODE_STARTED,
      data: { node: "planner" },
    });

    expect(updates.activityEvents).toHaveLength(1);
    expect(updates.activityEvents[0].node).toBe("planner");
  });

  it("sets pendingApproval on approval_required", () => {
    const approval = {
      reason: "Post comment",
      tool_name: "post_gitlab_mr_comment",
    };
    const updates = applyStreamEvent(baseState, {
      event: STREAM_EVENTS.APPROVAL_REQUIRED,
      data: approval,
    });

    expect(updates.pendingApproval).toEqual(approval);
    expect(updates.isAwaitingApproval).toBe(true);
    expect(updates.isStreaming).toBe(false);
  });

  it("records plan step completion in activityEvents", () => {
    const updates = applyStreamEvent(baseState, {
      event: STREAM_EVENTS.PLAN_STEP_COMPLETED,
      data: { step_id: "s1" },
    });

    expect(updates.activityEvents).toHaveLength(1);
    expect(updates.shouldRefetchBootstrap).toBeUndefined();
  });

  it("tracks knowledge proposals", () => {
    const updates = applyStreamEvent(baseState, {
      event: STREAM_EVENTS.KNOWLEDGE_PROPOSED,
      data: { assertion_ids: ["a1"], count: 1 },
    });

    expect(updates.knowledgeManifest.proposed_assertion_ids).toEqual(["a1"]);
    expect(updates.activityEvents).toHaveLength(1);
  });

  it("finalizes streaming and refreshes bootstrap on done", () => {
    const updates = applyStreamEvent(baseState, {
      event: STREAM_EVENTS.DONE,
      data: { interrupted: false },
    });

    expect(updates.messages[0].streaming).toBe(false);
    expect(updates.isStreaming).toBe(false);
    expect(updates.shouldRefetchBootstrap).toBe(true);
  });

  it("captures stream errors", () => {
    const updates = applyStreamEvent(baseState, {
      event: STREAM_EVENTS.ERROR,
      data: { message: "node failed" },
    });

    expect(updates.error).toBe("node failed");
    expect(updates.isStreaming).toBe(false);
    expect(updates.messages[0].content).toBe("node failed");
    expect(updates.messages[0].streaming).toBe(false);
  });
});
