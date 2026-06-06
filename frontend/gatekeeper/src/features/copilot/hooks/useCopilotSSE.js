import { useCallback, useEffect, useRef, useState } from "react";
import {
  reconnectStream,
  streamAsk,
  streamResume,
} from "../api/copilotStream";
import { CONNECTION_STATUS } from "../constants/streamEvents";

function parseEventId(id) {
  if (id === undefined || id === null || id === "") {
    return null;
  }

  const parsed = Number.parseInt(String(id), 10);
  return Number.isNaN(parsed) ? null : parsed;
}

/**
 * Manages a single Copilot SSE connection lifecycle per conversation.
 */
export function useCopilotSSE({
  conversationId,
  enabled = true,
  onEvent,
  onError,
  onStreamDone,
}) {
  const [connectionStatus, setConnectionStatus] = useState(
    CONNECTION_STATUS.IDLE,
  );
  const [lastEventId, setLastEventId] = useState(null);

  const streamHandleRef = useRef(null);
  const lastEventIdRef = useRef(null);
  const onEventRef = useRef(onEvent);
  const onErrorRef = useRef(onError);
  const onStreamDoneRef = useRef(onStreamDone);

  useEffect(() => {
    onEventRef.current = onEvent;
    onErrorRef.current = onError;
    onStreamDoneRef.current = onStreamDone;
  }, [onEvent, onError, onStreamDone]);

  const disconnect = useCallback(() => {
    streamHandleRef.current?.abort();
    streamHandleRef.current = null;

    setConnectionStatus((status) =>
      status === CONNECTION_STATUS.IDLE
        ? CONNECTION_STATUS.IDLE
        : CONNECTION_STATUS.DISCONNECTED,
    );
  }, []);

  const trackEvent = useCallback((event) => {
    const parsedId = parseEventId(event.id);
    if (parsedId !== null) {
      lastEventIdRef.current = parsedId;
      setLastEventId(parsedId);
    }

    setConnectionStatus((current) =>
      current === CONNECTION_STATUS.CONNECTING
        ? CONNECTION_STATUS.CONNECTED
        : current,
    );

    onEventRef.current?.(event);
  }, []);

  const startStream = useCallback(
    (starter) => {
      if (!conversationId || !enabled) {
        return null;
      }

      disconnect();
      setConnectionStatus(CONNECTION_STATUS.CONNECTING);

      const handle = starter({
        conversationId,
        lastEventId: lastEventIdRef.current,
        onEvent: trackEvent,
        onError: (error) => {
          streamHandleRef.current = null;
          setConnectionStatus(CONNECTION_STATUS.ERROR);
          onErrorRef.current?.(error);
        },
        onDone: () => {
          streamHandleRef.current = null;
          setConnectionStatus(CONNECTION_STATUS.DISCONNECTED);
          onStreamDoneRef.current?.();
        },
      });

      streamHandleRef.current = handle;
      return handle;
    },
    [conversationId, enabled, disconnect, trackEvent],
  );

  const connectAsk = useCallback(
    (body) => startStream((options) => streamAsk({ ...options, body })),
    [startStream],
  );

  const connectResume = useCallback(
    (body) => startStream((options) => streamResume({ ...options, body })),
    [startStream],
  );

  const reconnect = useCallback(
    () =>
      startStream((options) =>
        reconnectStream({
          ...options,
          threadId: conversationId,
          lastEventId: lastEventIdRef.current,
        }),
      ),
    [startStream, conversationId],
  );

  useEffect(() => () => disconnect(), [disconnect]);

  useEffect(() => {
    disconnect();
    lastEventIdRef.current = null;
    setLastEventId(null);
    setConnectionStatus(CONNECTION_STATUS.IDLE);
  }, [conversationId, disconnect]);

  useEffect(() => {
    if (!enabled) {
      disconnect();
    }
  }, [enabled, disconnect]);

  return {
    connectAsk,
    connectResume,
    reconnect,
    disconnect,
    connectionStatus,
    lastEventId,
  };
}
