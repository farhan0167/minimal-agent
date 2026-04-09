import { parseSSEStream } from "../lib/sse";
import type { SSEEvent } from "../types/message";
import type { MessageHistoryResponse } from "../types/message";
import { apiFetch } from "./client";

/**
 * Send a user message and stream back SSE events from the agent.
 */
export async function* sendMessage(
  sessionId: string,
  message: string,
  signal: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const response = await apiFetch(`/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });

  yield* parseSSEStream(response, signal);
}

/**
 * Fetch the full message history for a session.
 */
export async function getMessages(
  sessionId: string,
): Promise<MessageHistoryResponse> {
  const res = await apiFetch(`/sessions/${sessionId}/messages`);
  return res.json();
}
