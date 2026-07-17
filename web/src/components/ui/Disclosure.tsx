import { useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";

/**
 * The expand/collapse.
 *
 * ToolCallCard and ReasoningPart both built this, and neither built it the same
 * way: one used a Chevron swap, the other a rotated "▸"; one announced
 * aria-expanded, the other didn't. Extracted so both — and every future
 * collapsed section — announce and animate identically.
 *
 * `variant` is the one real difference between the two: a tool card's summary
 * is a tinted header bar, a reasoning trace's is a quiet line of text. Same
 * mechanic, different clothes, so it is a variant rather than two components.
 *
 * The summary is a render prop taking `open` because ReasoningPart's header
 * changes content when expanded (it drops the one-line thought preview) — a
 * plain ReactNode couldn't express that without the caller tracking open state
 * separately, which is the duplication this is meant to remove.
 */

export type DisclosureVariant = "bar" | "inline";

interface DisclosureProps {
  summary: ReactNode | ((open: boolean) => ReactNode);
  defaultOpen?: boolean;
  variant?: DisclosureVariant;
  children: ReactNode;
  /** Layout only. */
  className?: string;
}

const TRIGGERS: Record<DisclosureVariant, string> = {
  bar: "flex items-center gap-2 w-full px-4 py-2.5 text-left bg-app-hover hover:bg-app-active",
  inline: "flex items-center gap-1 w-full min-w-0 text-left text-app-fg-muted hover:text-app-fg",
};

export function Disclosure({
  summary,
  defaultOpen = false,
  variant = "bar",
  children,
  className = "",
}: DisclosureProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={
          TRIGGERS[variant] +
          " transition-app focus-visible:outline-none focus-visible:ring-2 " +
          "focus-visible:ring-app-ring focus-visible:ring-inset"
        }
      >
        <ChevronRight
          aria-hidden
          className={
            "w-4 h-4 shrink-0 text-app-fg-muted transition-app " +
            (open ? "rotate-90" : "")
          }
        />
        {typeof summary === "function" ? summary(open) : summary}
      </button>
      {open && children}
    </div>
  );
}
