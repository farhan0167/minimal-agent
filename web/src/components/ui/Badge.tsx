import type { ReactNode } from "react";

/**
 * The pill.
 *
 * Absorbs the hand-rolled `inline-flex … rounded-full` span repeated across
 * Header, SessionItem, NewSessionDialog and ToolCallCard.
 *
 * --app-radius-badge is what makes this more than a color wrapper: it is the
 * pill-vs-square axis, the one token that lets a theme change the app's shape
 * rather than just its palette.
 *
 * Note on the accent variant: the old call sites used three different accent
 * alphas — 0.12/0.25 (SessionItem agent), 0.06/0.15 (backend), 0.08/0.19
 * (Header backend). Nothing distinguished them but drift, so they collapse
 * into one recipe here.
 */

export type BadgeVariant = "accent" | "neutral" | "success" | "danger";
export type BadgeSize = "sm" | "md";

interface BadgeProps {
  variant?: BadgeVariant;
  /** sm: dense metadata tags (session rows). md: standalone chips (header). */
  size?: BadgeSize;
  children: ReactNode;
  /** Layout only — never colors. */
  className?: string;
}

// font-label + label-voice: badges speak in the theme's micro-label voice —
// most themes answer it as their UI sans; a technical theme answers uppercase
// tracked mono, and every badge becomes a drafting eyebrow at once.
const BASE =
  "inline-flex items-center gap-1 shrink-0 py-0.5 " +
  "font-label label-voice font-medium rounded-badge border";

const SIZES: Record<BadgeSize, string> = {
  sm: "px-1.5 text-[10px]",
  md: "px-2 text-xs",
};

const VARIANTS: Record<BadgeVariant, string> = {
  accent: "bg-app-accent/10 text-app-accent border-app-accent/20",
  neutral: "bg-app-hover text-app-fg-muted border-app-border",
  success: "bg-app-success/10 text-app-success border-app-success/20",
  danger: "bg-app-danger/10 text-app-danger border-app-danger/20",
};

export function Badge({
  variant = "neutral",
  size = "sm",
  children,
  className = "",
}: BadgeProps) {
  return (
    <span
      className={[BASE, SIZES[size], VARIANTS[variant], className]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </span>
  );
}
