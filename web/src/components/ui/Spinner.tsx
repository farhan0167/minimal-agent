import { Loader2 } from "lucide-react";

/**
 * The wait.
 *
 * Three sites spin their own Loader2 at three sizes in two colours. Sized by
 * prop here, coloured from --app-accent-text once.
 *
 * `label` is not decoration: a spinner with no accessible name is a silent
 * pause for a screen reader. When a caller renders visible "Loading…" text
 * beside it, pass nothing and the spinner stays out of the announcement.
 */

interface SpinnerProps {
  size?: "sm" | "md";
  /** Announced to assistive tech. Omit when adjacent text already says it. */
  label?: string;
  /** Layout only. */
  className?: string;
}

const SIZES = {
  sm: "w-3.5 h-3.5",
  md: "w-5 h-5",
};

export function Spinner({ size = "sm", label, className = "" }: SpinnerProps) {
  return (
    <Loader2
      role={label ? "status" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={[
        "shrink-0 animate-spin text-app-accent-text",
        SIZES[size],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    />
  );
}
