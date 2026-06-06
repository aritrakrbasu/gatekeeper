/**
 * Copilot SSE streaming client.
 *
 * Uses fetch + ReadableStream (not apiRequest) so Bearer auth and
 * Last-Event-ID headers work on POST ask/resume and GET reconnect.
 */

import { API_BASE_URL } from "../../../services/api";
import { parseSSEBuffer } from "../utils/parseSSE";

function getAccessToken() {
  return localStorage.getItem("access_token");
}

function handleUnauthorized() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("user");
  window.location.href = "/login";
  throw new Error("Authentication expired. Please login again.");
}

function buildStreamHeaders({ lastEventId, includeJson = true } = {}) {
  const headers = {
    Accept: "text/event-stream",
  };

  if (includeJson) {
    headers["Content-Type"] = "application/json";
  }

  const token = getAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  if (lastEventId !== undefined && lastEventId !== null && lastEventId !== "") {
    headers["Last-Event-ID"] = String(lastEventId);
  }

  return headers;
}

async function assertStreamResponse(response) {
  if (response.status === 401) {
    handleUnauthorized();
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(
      errorData.detail || errorData.message || "Copilot stream request failed",
    );
  }

  if (!response.body) {
    throw new Error("Copilot stream response has no body");
  }
}

/**
 * Read an SSE response body and dispatch parsed events.
 */
export async function readSSEFromResponse(response, onEvent) {
  await assertStreamResponse(response);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const { events, remainder } = parseSSEBuffer(buffer);
    buffer = remainder;

    for (const event of events) {
      onEvent(event);
    }
  }

  if (buffer.trim()) {
    const { events } = parseSSEBuffer(`${buffer}\n\n`);
    for (const event of events) {
      onEvent(event);
    }
  }
}

function startStream({ url, method = "GET", body, lastEventId, onEvent, onError, onDone }) {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}${url}`, {
        method,
        headers: buildStreamHeaders({
          lastEventId,
          includeJson: method !== "GET",
        }),
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      await readSSEFromResponse(response, onEvent);
      onDone?.();
    } catch (error) {
      if (error?.name === "AbortError") {
        return;
      }
      onError?.(error);
    }
  })();

  return {
    abort: () => controller.abort(),
  };
}

/**
 * POST /conversations/{id}/ask — question stream with optional resume.
 */
export function streamAsk({
  conversationId,
  body,
  lastEventId,
  onEvent,
  onError,
  onDone,
}) {
  return startStream({
    url: `/api/copilot/conversations/${conversationId}/ask`,
    method: "POST",
    body,
    lastEventId,
    onEvent,
    onError,
    onDone,
  });
}

/**
 * POST /conversations/{id}/resume — approval resume stream.
 */
export function streamResume({
  conversationId,
  body,
  lastEventId,
  onEvent,
  onError,
  onDone,
}) {
  return startStream({
    url: `/api/copilot/conversations/${conversationId}/resume`,
    method: "POST",
    body,
    lastEventId,
    onEvent,
    onError,
    onDone,
  });
}

/**
 * Build reconnect-only stream URL with query fallbacks.
 */
export function buildReconnectStreamUrl(
  conversationId,
  { threadId, lastEventId } = {},
) {
  const params = new URLSearchParams();
  if (threadId) {
    params.set("thread_id", threadId);
  }
  if (lastEventId !== undefined && lastEventId !== null && lastEventId !== "") {
    params.set("last_event_id", String(lastEventId));
  }

  const query = params.toString();
  return `/api/copilot/conversations/${conversationId}/stream${
    query ? `?${query}` : ""
  }`;
}

/**
 * GET /conversations/{id}/stream — reconnect-only stream.
 */
export function reconnectStream({
  conversationId,
  threadId,
  lastEventId,
  onEvent,
  onError,
  onDone,
}) {
  return startStream({
    url: buildReconnectStreamUrl(conversationId, { threadId, lastEventId }),
    method: "GET",
    lastEventId,
    onEvent,
    onError,
    onDone,
  });
}
