import { useEffect, useMemo, useState, type MutableRefObject } from "react";
import {
  useLocalRuntime,
  SimpleImageAttachmentAdapter,
  CompositeAttachmentAdapter,
  type ChatModelAdapter,
  type ChatModelRunResult,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import type {
  AttachmentAdapter,
  CompleteAttachment,
  PendingAttachment,
} from "@assistant-ui/react";
import { parsePartialJsonObject } from "assistant-stream/utils";
import { sendMessage, getMessages } from "../api/chat";
import type { FileAttachment, ReasoningEffort } from "../api/chat";
import type { Message } from "../types/message";
import { isAbortError } from "../lib/abort";
import { getSessionTitle, setSessionTitle } from "../lib/session-titles";

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

  async send(attachment: PendingAttachment): Promise<CompleteAttachment> {
    return {
      ...attachment,
      status: { type: "complete" as const },
      content: [
        {
          type: "file" as const,
          filename: attachment.name,
          data: await getFileDataURL(attachment.file),
          mimeType: "application/pdf",
        },
      ],
    };
  }

  async remove() {
    // noop
  }
}

/**
 * End the event stream quietly when it is torn down. A stopped stream
 * (cancel button, navigation, dropped connection) is not an error — the
 * server commits the partial turn, and the snapshot yielded so far stays on
 * screen. Real failures propagate.
 */
async function* ignoreAborts<T>(events: AsyncGenerator<T>): AsyncGenerator<T> {
  try {
    yield* events;
  } catch (err) {
    if (!isAbortError(err)) throw err;
  }
}

/** Extract the display text of the first user message, for session titles. */
function firstUserText(messages: Message[]): string | null {
  const first = messages.find((m) => m.role === "user");
  if (!first) return null;
  if (typeof first.content === "string") return first.content;
  if (Array.isArray(first.content)) {
    const text = first.content
      .filter((part) => part.type === "text")
      .map((part) => part.text)
      .join(" ");
    return text || null;
  }
  return null;
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
      | { type: "reasoning"; text: string }
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

        // Reasoning leads the turn — surface it before this message's tool
        // calls and text, matching the order the model produced it.
        if (m.reasoning) {
          parts.push({ type: "reasoning", text: m.reasoning });
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

/** The per-turn reasoning knobs the composer controls own. `effort`
 *  undefined means "provider default" — nothing is sent for it. */
export type ReasoningState = { on: boolean; effort?: ReasoningEffort };

/**
 * Build a LocalRuntime wired to our FastAPI SSE backend.
 *
 * Loads existing message history on mount via initialMessages.
 * Each yield must contain the FULL cumulative content, not deltas.
 *
 * `reasoningRef` carries the live Thinking on/off + effort selection. It's a
 * ref, not a prop, so toggling reasoning doesn't rebuild the memoized adapter
 * (and thus the runtime) mid-conversation — the adapter reads `.current` at
 * send time.
 */
export function useChatRuntime(
  sessionId: string,
  reasoningRef: MutableRefObject<ReasoningState>,
) {
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
        const title = firstUserText(data.messages);
        if (title) setSessionTitle(sessionId, title);
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
              (part as { mimeType?: string }).mimeType === "application/pdf"
            ) {
              return [
                {
                  data: (part as { data: string }).data,
                  mime_type: "application/pdf",
                },
              ];
            }
            return [];
          }),
        );

        if (!userText && attachments.length === 0) return;

        // First message in a fresh session names it in the sidebar.
        if (userText && !getSessionTitle(sessionId)) {
          setSessionTitle(sessionId, userText);
        }

        let currentText = "";
        let reasoningText = "";
        const toolCalls: ContentPart[] = [];
        const toolCallIndex = new Map<string, number>();

        // Tool calls the model is still generating, keyed by the provider's
        // fragment index. The first fragment carries id + name; later ones
        // append incremental JSON string chunks to argsText. Cleared when
        // the committed assistant message arrives (it is authoritative).
        const partialToolCalls = new Map<
          number,
          { id: string | null; name: string | null; argsText: string }
        >();

        // Render in-flight tool calls as tool-call parts with best-effort
        // parsed args, so renderers can preview them (e.g. write_file
        // content filling in) before the call is complete. Fragments
        // missing their opening (id + name) can't be keyed or routed to a
        // renderer yet, so they stay hidden until it arrives.
        const partialParts = (): ContentPart[] =>
          [...partialToolCalls.entries()]
            .sort(([a], [b]) => a - b)
            .filter(([, p]) => p.id !== null && p.name !== null)
            .map(
              ([, p]) =>
                ({
                  type: "tool-call",
                  toolCallId: p.id!,
                  toolName: p.name!,
                  argsText: p.argsText,
                  args: (parsePartialJsonObject(p.argsText) ?? {}) as never,
                }) as ContentPart,
            );

        // Prepend the reasoning trace (when present) so it renders above the
        // tool calls and answer, matching the order the model produced it.
        const withReasoning = (parts: ContentPart[]): ContentPart[] =>
          reasoningText
            ? [
                { type: "reasoning" as const, text: reasoningText } as ContentPart,
                ...parts,
              ]
            : parts;

        // Cumulative snapshot of the whole turn: committed tool calls, then
        // in-flight ones, then the answer text (matching commit order).
        const snapshot = (): ChatModelRunResult => ({
          content: withReasoning([
            ...toolCalls,
            ...partialParts(),
            ...(currentText
              ? [{ type: "text" as const, text: currentText }]
              : []),
          ]),
        });

        const { on: reasoningOn, effort } = reasoningRef.current;

        for await (const event of ignoreAborts(
          sendMessage(
            sessionId,
            userText,
            abortSignal,
            attachments.length > 0 ? attachments : undefined,
            reasoningOn,
            reasoningOn ? effort : undefined,
          ),
        )) {
          switch (event.type) {
            case "reasoning": {
              // Thinking token — accumulate and yield a snapshot so the
              // reasoning block fills in live above the (still empty) answer.
              reasoningText += event.data.text;
              yield snapshot();
              break;
            }

            case "delta": {
              // Live token — append and yield a cumulative snapshot.
              currentText += event.data.text;
              yield snapshot();
              break;
            }

            case "tool_call_delta": {
              // Argument fragments of an in-flight tool call — fold them in
              // and yield so the tool card appears (and its args fill in)
              // while the model is still generating the call.
              for (const tcd of event.data.tool_calls) {
                let slot = partialToolCalls.get(tcd.index);
                if (!slot) {
                  slot = { id: null, name: null, argsText: "" };
                  partialToolCalls.set(tcd.index, slot);
                }
                if (tcd.id) slot.id = tcd.id;
                if (tcd.name) slot.name = tcd.name;
                if (tcd.arguments) slot.argsText += tcd.arguments;
              }
              yield snapshot();
              break;
            }

            case "assistant": {
              const msg = event.data;

              // The committed message is authoritative: replace the streamed
              // text rather than append (deltas already built it up).
              if (msg.content) {
                currentText = msg.content as string;
              }
              if (msg.reasoning) {
                reasoningText = msg.reasoning;
              }

              // The committed message carries the assembled tool calls —
              // drop the partial mirror built from deltas.
              partialToolCalls.clear();

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

              yield snapshot();
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

              yield snapshot();
              break;
            }

            case "error": {
              // Full traceback goes to the console for debugging; the chat
              // shows the one-line detail.
              console.error(
                "Agent error:",
                event.data.detail,
                event.data.traceback ?? "",
              );
              currentText += `\n\n**Error:** ${event.data.detail}`;
              yield {
                content: withReasoning([
                  { type: "text" as const, text: currentText },
                ]),
              };
              break;
            }

            case "done":
              break;
          }
        }
      },
    }),
    [sessionId, reasoningRef],
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
