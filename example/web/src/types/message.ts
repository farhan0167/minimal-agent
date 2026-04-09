import type { Usage } from "./session";

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface Message {
  role: "system" | "user" | "assistant" | "tool";
  content: string | null;
  tool_call_id?: string;
  tool_calls?: ToolCall[];
}

export interface MessageHistoryResponse {
  messages: Message[];
}

/** SSE event types emitted by POST /sessions/{id}/chat */
export type SSEEvent =
  | { type: "assistant"; data: Message }
  | { type: "tool_result"; data: Message }
  | { type: "error"; data: { detail: string; traceback?: string } }
  | { type: "done"; data: { usage: Usage } };
