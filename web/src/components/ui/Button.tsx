import type { ButtonHTMLAttributes, ReactNode } from "react";

/**
 * The button.
 *
 * Decides what a button *is* — padding, radius, hover treatment, transition,
 * and the focus ring — once, for every button in the app. Before this existed
 * the focus ring lived in 2 of 24 component files; it now ships with every
 * call site by construction rather than by remembering.
 *
 * Feature components pick a variant and a size. They do not pass colors: if a
 * call site needs one, that is a missing variant, and the fix belongs here.
 */

export type ButtonVariant = "primary" | "ghost" | "icon" | "danger";
export type ButtonSize = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Stretch to the container's width — the selectable-row shape. */
  block?: boolean;
  children?: ReactNode;
}

// Every button, regardless of variant: the focus ring is the point.
//
// Motion comes from the `transition-app` utility rather than a
// duration-[--app-transition] arbitrary value — --app-transition holds a
// duration *and* an easing ("140ms ease"), which Tailwind's duration-* slot
// cannot accept. The utility is defined once in index.css.
const BASE =
  "inline-flex items-center justify-center gap-2 font-medium " +
  "rounded-ctl transition-app " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-ring " +
  "focus-visible:ring-offset-1 focus-visible:ring-offset-app-bg " +
  "disabled:opacity-50 disabled:pointer-events-none";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-app-accent text-app-accent-fg hover:bg-app-accent-hover",
  ghost: "text-app-fg-muted hover:bg-app-hover hover:text-app-fg",
  // Chrome that is all icon: no ground until you touch it.
  icon: "text-app-fg-muted hover:bg-app-hover hover:text-app-fg",
  danger: "text-app-danger hover:bg-app-danger/10",
};

// Icon buttons are square — their padding is driven by the glyph, not by text.
const SIZES: Record<ButtonVariant, Record<ButtonSize, string>> = {
  primary: { sm: "px-3 py-1.5 text-xs", md: "px-4 py-2 text-sm" },
  ghost: { sm: "px-3 py-1.5 text-xs", md: "px-4 py-2 text-sm" },
  icon: { sm: "p-1", md: "p-1.5" },
  danger: { sm: "p-1", md: "px-4 py-2 text-sm" },
};

export function Button({
  variant = "ghost",
  size = "md",
  block = false,
  className = "",
  type = "button",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={[
        BASE,
        VARIANTS[variant],
        SIZES[variant][size],
        block ? "w-full" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children}
    </button>
  );
}
