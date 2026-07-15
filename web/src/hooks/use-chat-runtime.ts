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
import type {
  Message,
  ContentPart as ServerContentPart,
} from "../types/message";
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
 * Is the user-role message at `i` one the agent loop generated, rather than
 * one the human typed?
 *
 * The loop commits user-role messages mid-run: its flush of non-text parts
 * (images from an image/PDF read) which can't ride a `tool` message and so
 * land in the only API-legal slot — a user message after the tool batch.
 * Those belong *inside* the assistant turn, not in a bubble of their own.
 *
 * The tell is position, and specifically which neighbor precedes it. The
 * multimodal-tool-results spec guarantees the ordering
 * `assistant → tool → tool → user(parts)`, so a flush ALWAYS directly follows
 * a `tool` message. A typed message never does — it follows an assistant reply
 * or begins the conversation. Keying on the preceding tool message (not on the
 * parts being images-only) keeps this correct when the flush later carries
 * audio/file parts, which the spec reserves as a future path.
 */
/**
 * Convert server content parts (the wire format) into assistant-ui thread
 * parts. The single source of truth for this mapping — used by the typed
 * multimodal user branch, the harness-flush absorption in toThreadMessages,
 * and the live `user_parts` handler, so the live and reload renderings of the
 * same message can't drift apart. Parts outside the typed union surface as a
 * visible placeholder rather than disappearing.
 */
function convertContentParts(
  content: ServerContentPart[],
): ({ type: "text"; text: string } | { type: "image"; image: string })[] {
  return content.map((part) => {
    switch (part.type) {
      case "text":
        return { type: "text" as const, text: part.text };
      case "image_url":
        return { type: "image" as const, image: part.image_url.url };
      default:
        return { type: "text" as const, text: "[unsupported content]" };
    }
  });
}

function isHarnessParts(messages: Message[], i: number): boolean {
  const msg = messages[i];
  const prev = messages[i - 1];
  return (
    msg.role === "user" &&
    Array.isArray(msg.content) &&
    !!prev &&
    prev.role === "tool"
  );
}

type TurnPart =
  | { type: "text"; text: string }
  | { type: "reasoning"; text: string }
  | { type: "image"; image: string }
  | {
      type: "tool-call";
      toolCallId: string;
      toolName: string;
      argsText: string;
      args: Record<string, unknown>;
      result?: unknown;
    };

/**
 * Flatten one agent turn — the committed messages between two typed user
 * messages — into ordered assistant-ui parts.
 *
 * The single source of truth for what a turn looks like. The reload path
 * (toThreadMessages) feeds it a slice of stored history; the live adapter
 * feeds it the mirror of messages committed so far mid-run. Because both
 * renderings come from the same walk, a refresh cannot rearrange a turn.
 *
 * Order is message order: each assistant message contributes its reasoning,
 * then its tool calls, then its text; tool results attach to their call by id;
 * a harness flush (user-role, see isHarnessParts) contributes its parts where
 * it sits in the sequence.
 */
function turnToParts(turn: Message[]): TurnPart[] {
  const toolResults = new Map<string, string>();
  for (const m of turn) {
    if (m.role === "tool" && m.tool_call_id) {
      toolResults.set(m.tool_call_id, (m.content as string) ?? "");
    }
  }

  const parts: TurnPart[] = [];
  for (const m of turn) {
    if (m.role === "user" && Array.isArray(m.content)) {
      parts.push(...convertContentParts(m.content));
    }
    if (m.role !== "assistant") continue;

    if (m.reasoning) {
      parts.push({ type: "reasoning", text: m.reasoning });
    }
    for (const tc of m.tool_calls ?? []) {
      parts.push({
        type: "tool-call",
        toolCallId: tc.id,
        toolName: tc.name,
        argsText: JSON.stringify(tc.arguments),
        args: tc.arguments,
        result: toolResults.get(tc.id),
      });
    }
    if (m.content) {
      parts.push({ type: "text", text: m.content as string });
    }
  }
  return parts;
}

/**
 * Convert stored server history to assistant-ui ThreadMessageLike format.
 *
 * Typed user messages become user bubbles. Everything between them — the
 * assistant's tool-call batches, tool results, interleaved commentary, and
 * any harness image flush — is one agent turn, rendered as ONE assistant
 * message whose parts sit in true message order (turnToParts). The live
 * adapter yields the same shape, so live and reloaded turns match.
 */
function toThreadMessages(messages: Message[]): readonly ThreadMessageLike[] {
  const result: ThreadMessageLike[] = [];

  let i = 0;
  while (i < messages.length) {
    const msg = messages[i];

    if (msg.role === "system") {
      i++;
      continue;
    }

    if (msg.role === "user" && !isHarnessParts(messages, i)) {
      if (Array.isArray(msg.content)) {
        // Multimodal user message — convert server content parts.
        result.push({ role: "user", content: convertContentParts(msg.content) });
      } else {
        result.push({
          role: "user",
          content: (msg.content as string) ?? "",
        });
      }
      i++;
      continue;
    }

    // Agent turn: consume up to the next typed user message.
    const start = i;
    while (
      i < messages.length &&
      (messages[i].role !== "user" || isHarnessParts(messages, i))
    ) {
      i++;
    }
    const parts = turnToParts(messages.slice(start, i));

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

        // Mirror of the turn's committed messages, exactly as the server
        // stores them. Snapshots derive their rendered parts from this via
        // turnToParts — the same function the reload path uses — so the live
        // rendering and the post-refresh rendering cannot drift apart.
        const turn: Message[] = [];

        // In-flight state for the message the model is still generating.
        // Deltas accumulate here; the committed `assistant` event moves the
        // authoritative version into `turn` and these reset.
        let pendingText = "";
        let pendingReasoning = "";

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

        // Cumulative snapshot of the whole turn: the committed messages in
        // true message order, then the message still being generated —
        // its streamed reasoning, in-flight tool calls, and streamed text,
        // in the same relative order turnToParts gives them once committed,
        // so nothing jumps around when the commit lands.
        const snapshot = (): ChatModelRunResult => ({
          content: [
            ...turnToParts(turn),
            ...(pendingReasoning
              ? [{ type: "reasoning" as const, text: pendingReasoning }]
              : []),
            ...partialParts(),
            ...(pendingText
              ? [{ type: "text" as const, text: pendingText }]
              : []),
          ] as NonNullable<ChatModelRunResult["content"]>,
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
              pendingReasoning += event.data.text;
              yield snapshot();
              break;
            }

            case "delta": {
              // Live token — append and yield a cumulative snapshot.
              pendingText += event.data.text;
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
              // The committed message is authoritative — move it into the
              // turn mirror and drop the streamed mirrors of its text,
              // reasoning, and tool calls (deltas already built them up).
              turn.push(event.data);
              pendingText = "";
              pendingReasoning = "";
              partialToolCalls.clear();
              yield snapshot();
              break;
            }

            case "tool_result": {
              // turnToParts attaches the result to its call by tool_call_id.
              turn.push(event.data);
              yield snapshot();
              break;
            }

            case "user_parts": {
              // The loop's post-batch flush (images from an image/PDF read).
              // It sits in the mirror where it sits in the stored history, so
              // its parts render inline at the same spot live and on reload.
              turn.push(event.data);
              yield snapshot();
              break;
            }

            case "error": {
              // Full traceback goes to the console for debugging; the chat
              // shows the one-line detail at the end of the turn.
              console.error(
                "Agent error:",
                event.data.detail,
                event.data.traceback ?? "",
              );
              pendingText += `\n\n**Error:** ${event.data.detail}`;
              yield snapshot();
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
