import { STREAM_EVENTS } from "../constants/streamEvents";

/**
 * Build initial message list from bootstrap conversation checkpoint.
 */
export function hydrateMessagesFromBootstrap(bootstrap) {
  if (!bootstrap?.conversation) {
    return [];
  }

  const messages = [];
  const { last_question: lastQuestion, response_text: responseText } =
    bootstrap.conversation;

  if (lastQuestion) {
    messages.push({
      id: "bootstrap-user",
      role: "user",
      content: lastQuestion,
    });
  }

  if (responseText) {
    messages.push({
      id: "bootstrap-assistant",
      role: "assistant",
      content: responseText,
    });
  }

  return messages;
}

/**
 * Pick the most recent resumable conversation for a repository.
 */
export function pickResumableConversation(items = []) {
  const resumable = items.filter((item) =>
    ["running", "waiting_approval"].includes(item.status),
  );

  if (resumable.length === 0) {
    return null;
  }

  return resumable.sort(
    (a, b) => new Date(b.last_updated) - new Date(a.last_updated),
  )[0];
}

function appendResponseChunk(messages, text, streamingMessageId) {
  if (!text) {
    return messages;
  }

  const next = [...messages];
  const streamingIndex = streamingMessageId
    ? next.findIndex((message) => message.id === streamingMessageId)
    : -1;

  if (streamingIndex >= 0) {
    const current = next[streamingIndex];
    next[streamingIndex] = {
      ...current,
      content: `${current.content}${text}`,
      streaming: true,
    };
    return next;
  }

  const lastIndex = next.length - 1;
  if (lastIndex >= 0 && next[lastIndex].role === "assistant") {
    const current = next[lastIndex];
    next[lastIndex] = {
      ...current,
      content: `${current.content}${text}`,
      streaming: true,
    };
    return next;
  }

  next.push({
    id: `assistant-chunk-${Date.now()}`,
    role: "assistant",
    content: text,
    streaming: true,
  });
  return next;
}

function finalizeStreamingMessage(messages, streamingMessageId) {
  const next = [...messages];
  const index = streamingMessageId
    ? next.findIndex((message) => message.id === streamingMessageId)
    : next.length - 1;

  if (index >= 0 && next[index]?.role === "assistant") {
    next[index] = { ...next[index], streaming: false };
  }

  return next;
}

function appendActivityEvent(activityEvents, event) {
  return [
    ...activityEvents,
    {
      id: event.id,
      type: event.event,
      node: event.data?.node,
      detail: event.data?.detail,
      message: event.data?.message,
      timestamp: new Date().toISOString(),
      data: event.data,
    },
  ];
}

/**
 * Pure stream-event reducer used by useCopilotSession.
 *
 * @returns {{ messages?, activityEvents?, pendingApproval?, isAwaitingApproval?, isStreaming?, error?, knowledgeManifest?, shouldRefetchBootstrap? }}
 */
export function applyStreamEvent(state, event) {
  const { event: type, data = {} } = event;
  const updates = {};

  switch (type) {
    case STREAM_EVENTS.RESPONSE_CHUNK:
      updates.messages = appendResponseChunk(
        state.messages,
        data.text,
        state.streamingMessageId,
      );
      break;

    case STREAM_EVENTS.NODE_STARTED:
    case STREAM_EVENTS.NODE_COMPLETED:
      updates.activityEvents = appendActivityEvent(state.activityEvents, event);
      break;

    case STREAM_EVENTS.APPROVAL_REQUIRED:
      updates.pendingApproval = data;
      updates.isAwaitingApproval = true;
      updates.isStreaming = false;
      break;

    case STREAM_EVENTS.INTERRUPTED:
      updates.isAwaitingApproval = true;
      updates.isStreaming = false;
      break;

    case STREAM_EVENTS.PLAN_STEP_COMPLETED:
      updates.shouldRefetchBootstrap = true;
      break;

    case STREAM_EVENTS.KNOWLEDGE_PROPOSED:
      updates.activityEvents = appendActivityEvent(state.activityEvents, event);
      updates.knowledgeManifest = {
        ...state.knowledgeManifest,
        proposed_assertion_ids: data.assertion_ids ?? [],
        proposed_count: data.count ?? 0,
      };
      break;

    case STREAM_EVENTS.DONE:
      updates.messages = finalizeStreamingMessage(
        state.messages,
        state.streamingMessageId,
      );
      updates.isStreaming = false;
      updates.isAwaitingApproval = Boolean(data.interrupted);
      updates.shouldRefetchBootstrap = true;
      break;

    case STREAM_EVENTS.ERROR:
      updates.error = data.message || "Copilot stream failed";
      updates.isStreaming = false;
      updates.activityEvents = appendActivityEvent(state.activityEvents, event);
      break;

    default:
      break;
  }

  return updates;
}
