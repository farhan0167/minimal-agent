import { useId } from "react";

/**
 * The toggle.
 *
 * Today's single instance is a raw <button> with inline-style translateX, no
 * focus ring, and a colour picked by a JS ternary rather than a token. The
 * settings UI will multiply it, so it gets built once with the keyboard and
 * ARIA story baked in.
 *
 * role="switch" + aria-checked is the whole reason this is a <button> and not a
 * checkbox: it announces "on/off", not "checked", which is what a Thinking
 * toggle means. The knob is aria-hidden — it is a picture of the state the
 * button already announces.
 */

interface SwitchProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  /** Rendered beside the switch and wired as its accessible name. */
  label?: string;
  disabled?: boolean;
  /** Layout only. */
  className?: string;
}

export function Switch({
  checked,
  onChange,
  label,
  disabled = false,
  className = "",
}: SwitchProps) {
  const labelId = useId();

  return (
    <span className={["inline-flex items-center gap-2", className].filter(Boolean).join(" ")}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={label ? labelId : undefined}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={
          "relative inline-flex h-4 w-7 shrink-0 items-center rounded-badge " +
          "transition-app focus-visible:outline-none focus-visible:ring-2 " +
          "focus-visible:ring-app-ring focus-visible:ring-offset-1 " +
          "focus-visible:ring-offset-app-bg " +
          "disabled:opacity-50 disabled:cursor-not-allowed " +
          (checked ? "bg-app-accent" : "bg-app-border-opaque")
        }
      >
        {/* The knob rides on the accent's foreground so it stays legible on a
            light accent — the same reason --app-accent-fg exists for buttons. */}
        <span
          aria-hidden
          className={
            "inline-block h-3 w-3 rounded-badge bg-app-accent-fg transition-app " +
            (checked ? "translate-x-3.5" : "translate-x-0.5")
          }
        />
      </button>
      {label && (
        <span id={labelId} className="font-ui text-xs font-medium">
          {label}
        </span>
      )}
    </span>
  );
}
