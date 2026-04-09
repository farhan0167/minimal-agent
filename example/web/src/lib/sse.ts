import type { SSEEvent, Message } from "../types/message";
import type { Usage } from "../types/session";

/**
 * Parse an SSE stream from a fetch Response into typed events.
 *
 * This is a pure async generator with no React dependency.
 * It reads the response body as text, splits on SSE boundaries,
 * and yields typed SSEEvent objects.
 */
export async function* parseSSEStream(
  response: Response,
  signal: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Response body is not readable");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      if (signal.aborted) break;

      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

      // SSE events are separated by double newlines.
      const parts = buffer.split("\n\n");
      // Last part may be incomplete — keep it in the buffer.
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        const event = parseSSEBlock(part.trim());
        if (event) yield event;
      }
    }

    // Flush remaining buffer.
    if (buffer.trim()) {
      const event = parseSSEBlock(buffer.trim());
      if (event) yield event;
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Parse a single SSE text block into a typed event.
 *
 * Expected format:
 *   event: <type>
 *   data: <json>
 */
function parseSSEBlock(block: string): SSEEvent | null {
  let eventType = "";
  const dataLines: string[] = [];

  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      eventType = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }

  const dataStr = dataLines.join("\n");

  if (!eventType || !dataStr) return null;

  try {
    const data: unknown = JSON.parse(dataStr);

    switch (eventType) {
      case "assistant":
        return { type: "assistant", data: data as Message };
      case "tool_result":
        return { type: "tool_result", data: data as Message };
      case "error":
        return {
          type: "error",
          data: data as { detail: string; traceback?: string },
        };
      case "done":
        return { type: "done", data: data as { usage: Usage } };
      default:
        return null;
    }
  } catch {
    return null;
  }
}
