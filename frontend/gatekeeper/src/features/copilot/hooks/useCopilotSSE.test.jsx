import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { CONNECTION_STATUS } from "../constants/streamEvents";

vi.mock("../api/copilotStream", () => ({
  streamAsk: vi.fn(),
  streamResume: vi.fn(),
  reconnectStream: vi.fn(),
}));

import { streamAsk, streamResume, reconnectStream } from "../api/copilotStream";
import { useCopilotSSE } from "./useCopilotSSE";

function mockStream(returnEvent) {
  return vi.fn(({ onEvent, onDone }) => {
    if (returnEvent) {
      onEvent(returnEvent);
    }
    onDone?.();
    return { abort: vi.fn() };
  });
}

describe("useCopilotSSE", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("tracks lastEventId from streamed events", async () => {
    streamAsk.mockImplementation(
      mockStream({ id: "12", event: "done", data: {} }),
    );

    const { result } = renderHook(() =>
      useCopilotSSE({
        conversationId: "conv-1",
        enabled: true,
      }),
    );

    act(() => {
      result.current.connectAsk({ question: "Why?" });
    });

    await waitFor(() => expect(result.current.lastEventId).toBe(12));
  });

  it("disconnects when enabled becomes false", () => {
    const abort = vi.fn();
    streamAsk.mockImplementation(() => ({ abort }));

    const { result, rerender } = renderHook(
      ({ enabled }) =>
        useCopilotSSE({
          conversationId: "conv-1",
          enabled,
        }),
      { initialProps: { enabled: true } },
    );

    act(() => {
      result.current.connectAsk({ question: "Why?" });
    });

    rerender({ enabled: false });

    expect(abort).toHaveBeenCalled();
    expect(result.current.connectionStatus).toBe(CONNECTION_STATUS.DISCONNECTED);
  });

  it("resets lastEventId when conversation changes", async () => {
    streamAsk.mockImplementation(
      mockStream({ id: "3", event: "done", data: {} }),
    );

    const { result, rerender } = renderHook(
      ({ conversationId }) =>
        useCopilotSSE({
          conversationId,
          enabled: true,
        }),
      { initialProps: { conversationId: "conv-1" } },
    );

    act(() => {
      result.current.connectAsk({ question: "Why?" });
    });

    await waitFor(() => expect(result.current.lastEventId).toBe(3));

    rerender({ conversationId: "conv-2" });

    expect(result.current.lastEventId).toBeNull();
    expect(result.current.connectionStatus).toBe(CONNECTION_STATUS.IDLE);
  });

  it("does not send Last-Event-ID for fresh ask requests", () => {
    streamAsk.mockImplementation(mockStream());

    const { result } = renderHook(() =>
      useCopilotSSE({
        conversationId: "conv-1",
        enabled: true,
      }),
    );

    act(() => {
      result.current.connectAsk({ question: "New question" });
    });

    expect(streamAsk).toHaveBeenCalledWith(
      expect.objectContaining({
        lastEventId: null,
        body: { question: "New question" },
      }),
    );
  });

  it("sends Last-Event-ID when reconnecting", () => {
    streamAsk.mockImplementation(
      mockStream({ id: "5", event: "done", data: {} }),
    );
    reconnectStream.mockImplementation(mockStream());

    const { result } = renderHook(() =>
      useCopilotSSE({
        conversationId: "conv-1",
        enabled: true,
      }),
    );

    act(() => {
      result.current.connectAsk({ question: "First" });
    });

    act(() => {
      result.current.reconnect();
    });

    expect(reconnectStream).toHaveBeenCalledWith(
      expect.objectContaining({
        lastEventId: 5,
      }),
    );
  });

  it("exposes connectResume and reconnect helpers", () => {
    streamResume.mockImplementation(mockStream());
    reconnectStream.mockImplementation(mockStream());

    const { result } = renderHook(() =>
      useCopilotSSE({
        conversationId: "conv-1",
        enabled: true,
      }),
    );

    act(() => {
      result.current.connectResume({ decision: "approve" });
      result.current.reconnect();
    });

    expect(streamResume).toHaveBeenCalled();
    expect(reconnectStream).toHaveBeenCalled();
  });
});
