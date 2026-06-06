/**
 * Parse a single SSE message block into a normalized event object.
 *
 * @param {string} block - Raw SSE block (lines separated by \n)
 * @returns {{ id?: string, event: string, data: object } | null}
 */
export function parseSSEBlock(block) {
  if (!block?.trim()) {
    return null;
  }

  const lines = block.split("\n");
  let id;
  let event;
  let data = "";

  for (const line of lines) {
    if (line.startsWith("id:")) {
      id = line.slice(3).trim();
    } else if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      const chunk = line.slice(5).trimStart();
      data = data ? `${data}\n${chunk}` : chunk;
    }
  }

  let parsedData = {};
  if (data) {
    try {
      parsedData = JSON.parse(data);
    } catch {
      parsedData = { raw: data };
    }
  }

  return {
    id,
    event: event || "message",
    data: parsedData,
  };
}

/**
 * Parse a buffered SSE payload into complete events and a remainder.
 *
 * @param {string} buffer - Accumulated SSE text
 * @returns {{ events: Array<{ id?: string, event: string, data: object }>, remainder: string }}
 */
export function parseSSEBuffer(buffer) {
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";
  const events = [];

  for (const part of parts) {
    const event = parseSSEBlock(part);
    if (event) {
      events.push(event);
    }
  }

  return { events, remainder };
}
