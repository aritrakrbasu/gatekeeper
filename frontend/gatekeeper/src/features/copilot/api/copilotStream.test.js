import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  readSSEFromResponse,
  streamAsk,
  streamResume,
  reconnectStream,
  buildReconnectStreamUrl,
} from "./copilotStream";

function createSSEResponse(chunks, { status = 200 } = {}) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });

  return new Response(stream, {
    status,
    headers: { "Content-Type": "text/event-stream" },
  });
}

describe("buildReconnectStreamUrl", () => {
  it("includes thread_id and last_event_id query params", () => {
    expect(
      buildReconnectStreamUrl("conv-1", {
        threadId: "conv-1",
        lastEventId: 12,
      }),
    ).toBe(
      "/api/copilot/conversations/conv-1/stream?thread_id=conv-1&last_event_id=12",
    );
  });
});

describe("readSSEFromResponse", () => {
  it("dispatches parsed SSE events", async () => {
    const events = [];
    const response = createSSEResponse([
      'id: 1\nevent: node_started\ndata: {"node":"planner"}\n\n',
      'id: 2\nevent: done\ndata: {"status":"completed"}\n\n',
    ]);

    await readSSEFromResponse(response, (event) => events.push(event));

    expect(events).toHaveLength(2);
    expect(events[0].event).toBe("node_started");
    expect(events[1].data.status).toBe("completed");
  });

  it("throws on non-OK responses", async () => {
    const response = new Response(JSON.stringify({ detail: "forbidden" }), {
      status: 403,
      headers: { "Content-Type": "application/json" },
    });

    await expect(
      readSSEFromResponse(response, () => {}),
    ).rejects.toThrow("forbidden");
  });
});

describe("stream clients", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    localStorage.setItem("access_token", "test-token");
    global.fetch = vi.fn();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("streamAsk POSTs with auth and Last-Event-ID headers", async () => {
    const events = [];
    global.fetch.mockResolvedValue(
      createSSEResponse(['id: 1\nevent: done\ndata: {}\n\n']),
    );

    const handle = streamAsk({
      conversationId: "conv-1",
      body: { question: "Why?" },
      lastEventId: 7,
      onEvent: (event) => events.push(event),
    });

    await vi.waitFor(() => expect(events).toHaveLength(1));

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/copilot/conversations/conv-1/ask",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer test-token",
          "Last-Event-ID": "7",
          Accept: "text/event-stream",
        }),
        body: JSON.stringify({ question: "Why?" }),
      }),
    );

    handle.abort();
  });

  it("streamResume POSTs to resume endpoint", async () => {
    global.fetch.mockResolvedValue(
      createSSEResponse(['id: 2\nevent: done\ndata: {}\n\n']),
    );

    streamResume({
      conversationId: "conv-1",
      body: { decision: "approve" },
      onEvent: () => {},
    });

    await vi.waitFor(() => expect(global.fetch).toHaveBeenCalled());

    expect(global.fetch.mock.calls[0][0]).toBe(
      "/api/copilot/conversations/conv-1/resume",
    );
    expect(global.fetch.mock.calls[0][1].method).toBe("POST");
  });

  it("reconnectStream GETs reconnect endpoint", async () => {
    global.fetch.mockResolvedValue(
      createSSEResponse(['id: 3\nevent: message\ndata: {}\n\n']),
    );

    reconnectStream({
      conversationId: "conv-1",
      threadId: "conv-1",
      lastEventId: 5,
      onEvent: () => {},
    });

    await vi.waitFor(() => expect(global.fetch).toHaveBeenCalled());

    expect(global.fetch.mock.calls[0][0]).toBe(
      "/api/copilot/conversations/conv-1/stream?thread_id=conv-1&last_event_id=5",
    );
    expect(global.fetch.mock.calls[0][1].method).toBe("GET");
    expect(global.fetch.mock.calls[0][1].headers["Last-Event-ID"]).toBe("5");
  });
});
