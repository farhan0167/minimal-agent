import { useId, type ReactNode, type SelectHTMLAttributes } from "react";
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

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
  /** Layout only. */
  wrapperClassName?: string;
}

/** The common case, so call sites don't write the render-prop dance. */
export function Select({
  label,
  hint,
  children,
  wrapperClassName = "",
  className = "",
  ...rest
}: SelectProps) {
  return (
    <Field label={label} hint={hint} className={wrapperClassName}>
      {({ id, className: control }) => (
        <select id={id} className={[control, className].filter(Boolean).join(" ")} {...rest}>
          {children}
        </select>
      )}
    </Field>
  );
}
