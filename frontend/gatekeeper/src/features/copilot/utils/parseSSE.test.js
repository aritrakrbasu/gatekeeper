import { describe, it, expect } from "vitest";
import { parseSSEBlock, parseSSEBuffer } from "./parseSSE";

describe("parseSSEBlock", () => {
  it("parses id, event, and JSON data", () => {
    const block = [
      "id: 42",
      "event: response_chunk",
      'data: {"text":"hello"}',
    ].join("\n");

    expect(parseSSEBlock(block)).toEqual({
      id: "42",
      event: "response_chunk",
      data: { text: "hello" },
    });
  });

  it("defaults event to message when omitted", () => {
    expect(parseSSEBlock('data: {"ok":true}')).toEqual({
      id: undefined,
      event: "message",
      data: { ok: true },
    });
  });

  it("wraps non-JSON data in raw field", () => {
    expect(parseSSEBlock("data: not-json")).toEqual({
      id: undefined,
      event: "message",
      data: { raw: "not-json" },
    });
  });
});

describe("parseSSEBuffer", () => {
  it("splits multiple complete events and keeps remainder", () => {
    const buffer =
      'id: 1\nevent: node_started\ndata: {"node":"planner"}\n\nid: 2\nevent: response_chunk\ndata: {"text":"hi"}\n\nid: 3\nevent: done\ndata:';

    const { events, remainder } = parseSSEBuffer(buffer);

    expect(events).toHaveLength(2);
    expect(events[0].id).toBe("1");
    expect(events[1].event).toBe("response_chunk");
    expect(remainder).toContain("id: 3");
  });

  it("returns empty events for incomplete buffer", () => {
    const { events, remainder } = parseSSEBuffer("id: 9\nevent: checkpoint");
    expect(events).toEqual([]);
    expect(remainder).toBe("id: 9\nevent: checkpoint");
  });
});
