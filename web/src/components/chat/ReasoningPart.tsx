import { useState, type ComponentType } from "react";
import type { ReasoningMessagePartProps } from "@assistant-ui/react";

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
 * slot — the prebuilt <Thread> has no reasoning support of its own. The
 * Markdown component reads the part text from assistant-ui's part context
 * (useMessagePartText accepts reasoning parts), so it takes no props.
 */
export function makeReasoningPart(Markdown: ComponentType) {
  return function ReasoningPart({ text, status }: ReasoningMessagePartProps) {
    const [open, setOpen] = useState(false);

    // Nothing to disclose yet — stay out of the layout entirely.
    if (!text) return null;

    const isThinking = status?.type === "running";
    const isInterrupted =
      status?.type === "incomplete" && status.reason === "cancelled";

    return (
      <div className="my-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex items-center gap-1 w-full min-w-0 text-xs text-[hsl(var(--aui-muted-foreground))] hover:text-[hsl(var(--aui-foreground))] transition-colors"
        >
          <span
            className="inline-block transition-transform"
            style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)" }}
          >
            ▸
          </span>
          <span className={isThinking ? "animate-pulse" : undefined}>
            {isThinking ? "Thinking…" : "Reasoning"}
          </span>
          {isInterrupted && <span className="italic">(interrupted)</span>}
          {isThinking && !open && (
            <span className="ml-2 truncate italic opacity-70">
              {tailOfThought(text)}
            </span>
          )}
        </button>

        {open && (
          <div className="mt-1.5 border-l-2 border-[hsl(var(--aui-border))] pl-3 text-sm text-[hsl(var(--aui-muted-foreground))]">
            <Markdown />
          </div>
        )}
      </div>
    );
  };
}
