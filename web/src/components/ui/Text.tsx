import type { ElementType, HTMLAttributes, ReactNode } from "react";

/**
 * The voice.
 *
 * Absorbs the ~20 hand-rolled `text-xs text-[muted-foreground]` spans and the
 * 8 sprinkled `font-serif` classes. Those two literals were the whole reason a
 * theme could not change the app's typography: `font-serif` names a *look*, so
 * a sans theme had to edit every file that said it. `prose` names a *role* and
 * reads --app-font-prose, so a theme answers the question instead.
 *
 * `as` exists because the right element is a document question, not a styling
 * one — a caption may be a <span> in a row and a <p> in a panel, and neither
 * should change how it looks.
 */

export type TextVariant = "prose" | "label" | "caption" | "code";

// `as` makes the element polymorphic, so the attributes that element accepts
// have to travel with it — htmlFor on a <label>, title on a truncated span.
// Colors and fonts are still the variant's call; className is layout only.
interface TextProps extends Omit<HTMLAttributes<HTMLElement>, "color"> {
  variant?: TextVariant;
  as?: ElementType;
  /** Muted where the variant is not already muted — the "secondary" axis. */
  muted?: boolean;
  children?: ReactNode;
  /** Present for `as="label"`; ignored by every other element. */
  htmlFor?: string;
  /** Layout only — never colors, never fonts. */
  className?: string;
}

const VARIANTS: Record<TextVariant, string> = {
  // The theme's voice: serif in claude, sans in graphite. Weight travels with
  // the face because a 450 serif and a 450 sans are not the same colour of grey.
  prose: "font-prose font-(--app-prose-weight) text-app-fg",
  label: "font-ui text-xs font-medium text-app-fg",
  caption: "font-ui text-xs text-app-fg-muted",
  code: "font-mono text-xs text-app-fg-muted",
};

// Defaults chosen so `as` is omitted at most call sites.
const ELEMENTS: Record<TextVariant, ElementType> = {
  prose: "p",
  label: "span",
  caption: "span",
  code: "code",
};

export function Text({
  variant = "prose",
  as,
  muted = false,
  children,
  className = "",
  ...rest
}: TextProps) {
  const Component = as ?? ELEMENTS[variant];
  return (
    <Component
      className={[VARIANTS[variant], muted ? "text-app-fg-muted" : "", className]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children}
    </Component>
  );
}
