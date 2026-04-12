import { useEffect, useMemo, useState } from "react";
import {
  useLocalRuntime,
  SimpleImageAttachmentAdapter,
  CompositeAttachmentAdapter,
  type ChatModelAdapter,
  type ChatModelRunResult,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import type { AttachmentAdapter } from "@assistant-ui/react";
import { sendMessage, getMessages } from "../api/chat";
import type { FileAttachment } from "../api/chat";
import type { Message } from "../types/message";

type ContentPart = NonNullable<ChatModelRunResult["content"]>[number];

const getFileDataURL = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = (error) => reject(error);
    reader.readAsDataURL(file);
  });

/**
 * Attachment adapter for PDF files.
 * Reads the PDF as a base64 data URI so the server can convert pages to images.
 */
class PdfAttachmentAdapter implements AttachmentAdapter {
  accept = "application/pdf";

  async add(state: { file: File }) {
    return {
      id: state.file.name,
      type: "document" as const,
      name: state.file.name,
      contentType: state.file.type,
      file: state.file,
      status: { type: "requires-action" as const, reason: "composer-send" as const },
    };
  }

  async send(attachment: { file: File; [key: string]: unknown }) {
    return {
      ...attachment,
      status: { type: "complete" as const },
      content: [
        {
          type: "file" as const,
          file: {
            data: await getFileDataURL(attachment.file),
            mimeType: "application/pdf",
          },
        },
      ],
    };
  }

  async remove() {
    // noop
  }
}

/**
 * Convert server messages to assistant-ui ThreadMessageLike format.
 *
 * The server stores messages as a flat sequence per agent turn:
 *   assistant {content:"", tool_calls:[...]}  → tool {result} → assistant {content:"final text"}
 *
 * We merge each such sequence into a single assistant ThreadMessageLike
 * containing tool-call parts (with results) + final text.
 */
function toThreadMessages(messages: Message[]): readonly ThreadMessageLike[] {
  const result: ThreadMessageLike[] = [];

  // Index tool results by tool_call_id for quick lookup.
  const toolResults = new Map<string, string>();
  for (const msg of messages) {
    if (msg.role === "tool" && msg.tool_call_id) {
      toolResults.set(msg.tool_call_id, (msg.content as string) ?? "");
    }
  }

  let i = 0;
  while (i < messages.length) {
    const msg = messages[i];

    // Skip system and tool messages (tool results are merged via the map).
    if (msg.role === "system" || msg.role === "tool") {
      i++;
      continue;
    }

    if (msg.role === "user") {
      if (Array.isArray(msg.content)) {
        // Multimodal user message — convert server content parts.
        const parts = msg.content.map((part) => {
          if (part.type === "text") {
            return { type: "text" as const, text: part.text };
          }
          if (part.type === "image_url") {
            return { type: "image" as const, image: part.image_url.url };
          }
          return { type: "text" as const, text: "[unsupported content]" };
        });
        result.push({ role: "user", content: parts });
      } else {
        result.push({
          role: "user",
          content: (msg.content as string) ?? "",
        });
      }
      i++;
      continue;
    }

    // Assistant message — collect this and any continuation into one turn.
    // A turn is: assistant(tool_calls) → tool(s) → assistant(text)
    // Or just: assistant(text) alone.
    const parts: (
      | { type: "text"; text: string }
      | {
          type: "tool-call";
          toolCallId: string;
          toolName: string;
          argsText: string;
          args: Record<string, unknown>;
          result?: unknown;
        }
    )[] = [];

    // Walk forward, merging assistant+tool messages into turns.
    // A single turn is: optional text + tool_calls + tool results + optional trailing text.
    // When a new assistant message with text (and no tool_calls) appears after
    // we've already accumulated parts, flush the current turn and start a new one.
    while (i < messages.length && messages[i].role !== "user") {
      const m = messages[i];

      if (m.role === "assistant") {
        const hasToolCalls = m.tool_calls && m.tool_calls.length > 0;
        const hasText = !!m.content;

        // If this assistant message has text but no tool calls, and we already
        // have accumulated parts, it's a new standalone turn — flush first.
        if (hasText && !hasToolCalls && parts.length > 0) {
          result.push({
            role: "assistant",
            content: parts.splice(0) as ThreadMessageLike["content"],
          });
        }

        if (hasToolCalls) {
          for (const tc of m.tool_calls!) {
            parts.push({
              type: "tool-call",
              toolCallId: tc.id,
              toolName: tc.name,
              argsText: JSON.stringify(tc.arguments),
              args: tc.arguments,
              result: toolResults.get(tc.id),
            });
          }
        }
        if (hasText) {
          parts.push({ type: "text", text: m.content as string });
        }
      }
      // Skip tool messages — already indexed above.
      i++;
    }

    if (parts.length > 0) {
      result.push({
        role: "assistant",
        content: parts as ThreadMessageLike["content"],
      });
    }
  }

  return result;
}

/**
 * Build a LocalRuntime wired to our FastAPI SSE backend.
 *
 * Loads existing message history on mount via initialMessages.
 * Each yield must contain the FULL cumulative content, not deltas.
 */
export function useChatRuntime(sessionId: string) {
  const [initialMessages, setInitialMessages] = useState<
    readonly ThreadMessageLike[]
  >([]);
  const [isLoaded, setIsLoaded] = useState(false);

  // Fetch message history when session changes.
  useEffect(() => {
    let cancelled = false;
    setIsLoaded(false);

    getMessages(sessionId)
      .then((data) => {
        if (cancelled) return;
        setInitialMessages(toThreadMessages(data.messages));
      })
      .catch(() => {
        if (cancelled) return;
        setInitialMessages([]);
      })
      .finally(() => {
        if (cancelled) return;
        setIsLoaded(true);
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const adapter = useMemo<ChatModelAdapter>(
    () => ({
      async *run({ messages, abortSignal }) {
        const lastMessage = messages[messages.length - 1];
        if (!lastMessage || lastMessage.role !== "user") return;

        const textParts = lastMessage.content.filter(
          (part) => part.type === "text",
        );
        const userText = textParts
          .map((p) => ("text" in p ? p.text : ""))
          .join("\n");

        // Extract attachments (images and PDFs) from the message.
        const rawAttachments =
          "attachments" in lastMessage ? lastMessage.attachments ?? [] : [];
        const attachments: FileAttachment[] = rawAttachments.flatMap((att) =>
          (att.content ?? []).flatMap((part): FileAttachment[] => {
            if (part.type === "image") {
              return [
                {
                  data: (part as { image: string }).image,
                  mime_type: att.contentType ?? "image/png",
                },
              ];
            }
            if (
              part.type === "file" &&
              "file" in part &&
              (part as { file: { mimeType: string } }).file.mimeType ===
                "application/pdf"
            ) {
              return [
                {
                  data: (part as { file: { data: string } }).file.data,
                  mime_type: "application/pdf",
                },
              ];
            }
            return [];
          }),
        );

        if (!userText && attachments.length === 0) return;

        let currentText = "";
        const toolCalls: ContentPart[] = [];
        const toolCallIndex = new Map<string, number>();

        for await (const event of sendMessage(
          sessionId,
          userText,
          abortSignal,
          attachments.length > 0 ? attachments : undefined,
        )) {
          switch (event.type) {
            case "assistant": {
              const msg = event.data;

              if (msg.content) {
                currentText = msg.content as string;
              }

              if (msg.tool_calls) {
                for (const tc of msg.tool_calls) {
                  toolCallIndex.set(tc.id, toolCalls.length);
                  toolCalls.push({
                    type: "tool-call",
                    toolCallId: tc.id,
                    toolName: tc.name,
                    argsText: JSON.stringify(tc.arguments),
                    args: tc.arguments as never,
                  } as ContentPart);
                }
              }

              yield {
                content: [
                  ...toolCalls,
                  ...(currentText
                    ? [{ type: "text" as const, text: currentText }]
                    : []),
                ],
              };
              break;
            }

            case "tool_result": {
              const msg = event.data;
              const tcId = msg.tool_call_id;
              if (tcId && toolCallIndex.has(tcId)) {
                const idx = toolCallIndex.get(tcId)!;
                const existing = toolCalls[idx] as Record<string, unknown>;
                toolCalls[idx] = {
                  ...existing,
                  result: msg.content,
                } as ContentPart;
              }

              yield {
                content: [
                  ...toolCalls,
                  ...(currentText
                    ? [{ type: "text" as const, text: currentText }]
                    : []),
                ],
              };
              break;
            }

            case "error": {
              currentText += `\n\n**Error:** ${event.data.detail}`;
              yield {
                content: [{ type: "text" as const, text: currentText }],
              };
              break;
            }

            case "done":
              break;
          }
        }
      },
    }),
    [sessionId],
  );

  const runtime = useLocalRuntime(adapter, {
    initialMessages,
    adapters: {
      attachments: new CompositeAttachmentAdapter([
        new SimpleImageAttachmentAdapter(),
        new PdfAttachmentAdapter(),
      ]),
    },
  });

  return { runtime, isLoaded };
}
