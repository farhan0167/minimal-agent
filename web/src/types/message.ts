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
  /** Provider "thinking" trace, when the agent was configured for reasoning. */
  reasoning?: string | null;
}

export interface MessageHistoryResponse {
  messages: Message[];
}

/**
 * A fragment of an in-flight tool call, streamed while the model is still
 * generating it. Fragments are keyed by `index`: the first one carries `id`
 * and `name`, later ones carry `arguments` as incremental JSON string chunks
 * to concatenate. The committed `assistant` event that follows is
 * authoritative and replaces whatever was accumulated.
 */
export interface ToolCallDelta {
  index: number;
  id?: string;
  name?: string;
  arguments?: string;
}

/** SSE event types emitted by POST /sessions/{id}/chat */
export type SSEEvent =
  | { type: "delta"; data: { text: string } }
  | { type: "reasoning"; data: { text: string } }
  | { type: "tool_call_delta"; data: { tool_calls: ToolCallDelta[] } }
  | { type: "assistant"; data: Message }
  | { type: "tool_result"; data: Message }
  /**
   * Non-text parts (images from an image/PDF read) that the agent loop flushes
   * after a tool batch. Harness-generated, not user-typed, despite the
   * user role it carries on the wire.
   */
  | { type: "user_parts"; data: Message }
  | { type: "error"; data: { detail: string; traceback?: string } }
  | { type: "done"; data: { usage: Usage } };
