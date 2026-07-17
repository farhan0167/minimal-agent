import type { ReactNode } from "react";

/**
 * The considered ground.
 *
 * Every container that is not just a <div>: cards, dialog panels, the chat's
 * user bubble, the composer frame. They look unrelated but differ only in which
 * radius and background token they read — which is exactly the thing a theme
 * wants to change, and exactly the thing that was hardcoded five different ways.
 *
 * `inset` is the odd one out: it is not a container with a ground so much as a
 * tint *of* its host (the `bg-[hsl(var(--claude-hover))]` blocks inside tool
 * cards). It lives here because it answers the same question — "what does a
 * nested region sit on" — and sharing the radius scale keeps it honest.
 */

export type SurfaceVariant =
  | "card"
  | "outline"
  | "panel"
  | "bubble"
  | "composer"
  | "inset";

interface SurfaceProps {
  variant?: SurfaceVariant;
  children?: ReactNode;
  /** Layout only — never colors, never radii. */
  className?: string;
}

const VARIANTS: Record<SurfaceVariant, string> = {
  card: "bg-app-surface border border-app-border rounded-surface overflow-hidden",
  // A bordered box that lets the page through: its ground comes from whatever
  // it wraps (a tool card's tinted header bar), not from a fill of its own.
  // Distinct from `card` because --app-surface is pure white in the claude
  // theme — filling it flattens the very tint that gives the box its shape.
  outline: "border border-app-border rounded-surface overflow-hidden",
  panel: "bg-app-bg border border-app-border rounded-surface shadow-(--app-shadow)",
  bubble: "bg-app-bubble-user rounded-bubble",
  composer: "bg-app-composer border border-app-border rounded-composer",
  inset: "bg-app-hover rounded-ctl",
};

export function Surface({
  variant = "card",
  children,
  className = "",
}: SurfaceProps) {
  return (
    <div className={[VARIANTS[variant], className].filter(Boolean).join(" ")}>
      {children}
    </div>
  );
}
