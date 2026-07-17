import { useId, type ReactNode, type SelectHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";
import { Text } from "./Text";

/**
 * The form control.
 *
 * One border, radius, padding, placeholder colour and focus treatment for every
 * input in the app. Today that is a select in NewSessionDialog and a select in
 * ReasoningControls, each with its own idea of all five.
 *
 * `label` is a prop rather than a slot because the label/control association is
 * the part call sites get wrong: useId wires htmlFor/id here so no feature file
 * has to remember. A control with a visible label is never left unlabelled.
 */

const CONTROL =
  "w-full px-3 py-2 text-sm font-ui " +
  "bg-app-composer text-app-fg " +
  "border border-app-border rounded-ctl transition-app " +
  "placeholder:text-app-fg-muted " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-ring " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

interface FieldProps {
  label?: ReactNode;
  hint?: ReactNode;
  children: (props: { id: string; className: string }) => ReactNode;
  /** Layout only. */
  className?: string;
}

/**
 * Wraps a control with its label and hint. The child is a function so the
 * caller keeps ownership of the element (a <select> and a <textarea> take
 * different props) while Field keeps ownership of how it looks.
 */
export function Field({ label, hint, children, className = "" }: FieldProps) {
  const id = useId();
  return (
    <div className={["flex flex-col gap-1.5", className].filter(Boolean).join(" ")}>
      {label && (
        <Text variant="label" as="label" muted htmlFor={id}>
          {label}
        </Text>
      )}
      {children({ id, className: CONTROL })}
      {hint && <Text variant="caption">{hint}</Text>}
    </div>
  );
}

/**
 * A <select> is the one control that can't reuse CONTROL as-is: the browser
 * draws its own chevron and native chrome (appearance:auto), which no border
 * or background token can reach — the result reads as a filled OS widget, not
 * a designed control. So Select resets appearance and draws its own chevron,
 * and offers a compact `toolbar` size for header/toolbar dropdowns that must
 * sit as lightly as the icon buttons beside them, not as filled form inputs.
 */
export type SelectSize = "field" | "toolbar";

// Shared by both sizes: kill the native widget so our chevron is the only one,
// and reserve room on the right for it.
const SELECT_BASE =
  "appearance-none bg-none pr-8 font-ui text-app-fg cursor-pointer " +
  "rounded-ctl transition-app " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-ring " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

const SELECT_SIZES: Record<SelectSize, string> = {
  // The form field: a full input with a visible border and ground.
  field: "w-full pl-3 py-2 text-sm bg-app-composer border border-app-border",
  // The toolbar control: no ground until hovered, so it reads as chrome.
  toolbar: "pl-2.5 py-1 text-xs bg-transparent hover:bg-app-hover",
};

// The chevron sits closer in the compact size to stay proportional.
const CHEVRON_SIZES: Record<SelectSize, string> = {
  field: "right-2.5 w-4 h-4",
  toolbar: "right-1.5 w-3.5 h-3.5",
};

// Omit the native `size` (a number — the visible-rows count) so our design
// `size` can name the variant instead; a dropdown never uses the native one.
interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> {
  label?: ReactNode;
  hint?: ReactNode;
  size?: SelectSize;
  children: ReactNode;
  /** Layout only. */
  wrapperClassName?: string;
}

/** The common case, so call sites don't write the render-prop dance. */
export function Select({
  label,
  hint,
  size = "field",
  children,
  wrapperClassName = "",
  className = "",
  ...rest
}: SelectProps) {
  const id = useId();
  return (
    <div
      className={[
        size === "toolbar" ? "flex items-center gap-1.5" : "flex flex-col gap-1.5",
        wrapperClassName,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {label && (
        <Text variant="label" as="label" muted htmlFor={id}>
          {label}
        </Text>
      )}
      {/* The chevron is a sibling of the <select>, absolutely positioned and
          click-through, so the whole control still opens the native picker. */}
      <div className="relative inline-flex">
        <select
          id={id}
          className={[SELECT_BASE, SELECT_SIZES[size], className].filter(Boolean).join(" ")}
          {...rest}
        >
          {children}
        </select>
        <ChevronDown
          aria-hidden
          className={
            "pointer-events-none absolute top-1/2 -translate-y-1/2 text-app-fg-muted " +
            CHEVRON_SIZES[size]
          }
        />
      </div>
      {hint && <Text variant="caption">{hint}</Text>}
    </div>
  );
}
