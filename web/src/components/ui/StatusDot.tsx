/**
 * The health indicator.
 *
 * Maps a status to a semantic token in one place. The value is not the eight
 * lines of CSS — it is that "error is red" stops being a decision each renderer
 * makes for itself, so a theme that wants a different red edits one token
 * instead of hunting for every place someone typed one.
 *
 * Status is declared here rather than imported from tools/ToolCallCard, whose
 * ToolStatus is structurally identical: a primitive that imports from a feature
 * points the floor upward, and the next consumer (a connection light, a health
 * badge) has nothing to do with tool calls. The vocabularies coincide today;
 * they are not the same idea.
 *
 * The dot is decorative: callers put it next to text that already says
 * "running" or "failed", so it is aria-hidden rather than adding a second
 * announcement of the same fact.
 */

export type Status = "running" | "complete" | "error" | "interrupted";

interface StatusDotProps {
  status: Status;
  /** Layout only. */
  className?: string;
}

const COLORS: Record<Status, string> = {
  running: "bg-app-accent-text motion-safe:animate-pulse",
  complete: "bg-app-success",
  error: "bg-app-danger",
  interrupted: "bg-app-fg-muted",
};

export function StatusDot({ status, className = "" }: StatusDotProps) {
  return (
    <span
      aria-hidden
      className={["inline-block w-2 h-2 rounded-badge shrink-0", COLORS[status], className]
        .filter(Boolean)
        .join(" ")}
    />
  );
}
