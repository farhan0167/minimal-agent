import { parseSSEStream } from "../lib/sse";
import type { SSEEvent } from "../types/message";
import type { MessageHistoryResponse } from "../types/message";
import { apiFetch } from "./client";

export interface FileAttachment {
  data: string; // base64 data URI
  mime_type: string; // e.g. "image/png", "application/pdf"
  detail?: "auto" | "low" | "high";
}

/**
 * Reasoning effort levels, mirroring the backend's neutral ReasoningEffort set.
 * The value passes through to the provider verbatim.
 */
export type ReasoningEffort =
  | "none"
  | "minimal"
  | "low"
  | "medium"
  | "high"
  | "xhigh";

/**
 * Send a user message and stream back SSE events from the agent.
 *
 * `reasoning` toggles whether a thinking trace is requested for this turn;
 * `effort` sets its level. Both are per-turn and no-op unless the agent was
 * configured with a reasoning contract on the server.
 */
export async function* sendMessage(
  sessionId: string,
  message: string,
  signal: AbortSignal,
  attachments?: FileAttachment[],
  reasoning?: boolean,
  effort?: ReasoningEffort,
): AsyncGenerator<SSEEvent> {
  const body: Record<string, unknown> = { message };
  if (attachments && attachments.length > 0) {
    body.attachments = attachments;
  }
  if (reasoning !== undefined) {
    body.reasoning = reasoning;
  }
  if (effort !== undefined) {
    body.effort = effort;
  }

  const response = await apiFetch(`/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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
