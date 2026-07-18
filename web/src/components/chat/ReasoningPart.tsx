import type { ReasoningMessagePartProps } from "@assistant-ui/react";
import { Disclosure } from "../ui/Disclosure";
import { MarkdownText } from "./MarkdownText";

/** Last non-empty line of the trace — a peek at the current thought. */
function tailOfThought(text: string): string {
  const lines = text.split("\n");
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].trim();
    if (line) return line;
  }
  return "";
}

/**
 * Renders an assistant "thinking" trace as a quiet, default-collapsed
 * disclosure that sits above the answer. While the model is thinking, the
 * collapsed header shows a live one-line preview of the latest thought;
 * expanding shows the full trace rendered as markdown.
 *
 * Wired into the assistant message via MessagePrimitive.Parts' `Reasoning`
 * slot. MarkdownText reads the part text from assistant-ui's part context
 * (useMessagePartText accepts reasoning parts), so it takes no props.
 */
export function ReasoningPart({ text, status }: ReasoningMessagePartProps) {
  // Nothing to disclose yet — stay out of the layout entirely.
  if (!text) return null;

  const isThinking = status?.type === "running";
  const isInterrupted =
    status?.type === "incomplete" && status.reason === "cancelled";

  return (
    <Disclosure
      variant="inline"
      className="my-2"
      // The preview is only meaningful while collapsed *and* still thinking;
      // once open, the full trace below says it better.
      summary={(open) => (
        <>
          <span
            className={`chat-reasoning-label text-xs ${isThinking ? "motion-safe:animate-pulse" : ""}`}
          >
            {isThinking ? "Thinking…" : "Reasoning"}
          </span>
          {isInterrupted && <span className="text-xs italic">(interrupted)</span>}
          {isThinking && !open && (
            <span className="ml-2 truncate text-xs italic opacity-70">
              {tailOfThought(text)}
            </span>
          )}
        </>
      )}
    >
      <div className="mt-1.5 border-l-2 border-app-border pl-3 text-sm text-app-fg-muted">
        <MarkdownText />
      </div>
    </Disclosure>
  );
}
