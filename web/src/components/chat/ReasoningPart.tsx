import { useState } from "react";
import type { ReasoningMessagePartProps } from "@assistant-ui/react";

/**
 * Renders an assistant "thinking" trace as a quiet, always-collapsed
 * disclosure that sits above the answer. The user can expand it on demand;
 * it never steals attention from the reply.
 *
 * Wired into the assistant message via MessagePrimitive.Parts' `Reasoning`
 * slot — the prebuilt <Thread> has no reasoning support of its own.
 */
export function ReasoningPart({ text }: ReasoningMessagePartProps) {
  const [open, setOpen] = useState(false);

  // Nothing to disclose yet — stay out of the layout entirely.
  if (!text) return null;

  return (
    <div className="my-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex items-center gap-1 text-xs text-[hsl(var(--aui-muted-foreground))] hover:text-[hsl(var(--aui-foreground))] transition-colors"
      >
        <span
          className="inline-block transition-transform"
          style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)" }}
        >
          ▸
        </span>
        Reasoning
      </button>

      {open && (
        <div className="mt-1.5 border-l-2 border-[hsl(var(--aui-border))] pl-3 text-sm text-[hsl(var(--aui-muted-foreground))] whitespace-pre-wrap">
          {text}
        </div>
      )}
    </div>
  );
}
