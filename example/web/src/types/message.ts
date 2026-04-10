import type { Usage } from "./session";

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

/** A text segment in a multimodal message. */
export interface TextContentPart {
  type: "text";
  text: string;
}

/** An image segment in a multimodal message. */
export interface ImageContentPart {
  type: "image_url";
  image_url: { url: string; detail?: "auto" | "low" | "high" };
}

export type ContentPart = TextContentPart | ImageContentPart;

export interface Message {
  role: "system" | "user" | "assistant" | "tool";
  content: string | ContentPart[] | null;
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
