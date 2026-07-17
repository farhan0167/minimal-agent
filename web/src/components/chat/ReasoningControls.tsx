import type { ReasoningEffort } from "../../api/chat";
import type { ReasoningState } from "../../hooks/use-chat-runtime";
import { Switch } from "../ui/Switch";
import { Select } from "../ui/Field";

/** Effort levels offered in the dropdown, in ascending order. The values are
 *  the neutral ReasoningEffort vocabulary; labels are the human-facing names.
 *  "Default" ("") means no effort is sent — the provider's own default
 *  applies, matching the pre-toggle behavior. */
const EFFORT_OPTIONS: { value: ReasoningEffort | ""; label: string }[] = [
  { value: "", label: "Default" },
  { value: "minimal", label: "Minimal" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "xhigh", label: "Max" },
];

interface ReasoningControlsProps {
  value: ReasoningState;
  onChange: (next: ReasoningState) => void;
}

/**
 * A "Thinking" toggle plus an effort selector for the current turn.
 *
 * Lives in the composer's bottom row, beside the attach button — the input is
 * where you decide how the next turn should think. The state lives in
 * ChatPanel (it must outlive the composer and reach the runtime adapter at
 * send time — see use-chat-runtime) and threads down via Thread → Composer.
 */
export function ReasoningControls({ value, onChange }: ReasoningControlsProps) {
  const { on, effort } = value;

  return (
    <div className="flex items-center gap-3">
      <Switch
        checked={on}
        onChange={(next) => onChange({ ...value, on: next })}
        label="Thinking"
      />

      {/* Effort is meaningless with thinking off; it fades rather than
          disappearing so the toolbar doesn't reflow on every toggle. */}
      <Select
        size="toolbar"
        label="Effort"
        value={effort ?? ""}
        disabled={!on}
        onChange={(e) =>
          onChange({
            ...value,
            effort: e.target.value
              ? (e.target.value as ReasoningEffort)
              : undefined,
          })
        }
        wrapperClassName={`transition-app ${on ? "opacity-100" : "opacity-40"}`}
      >
        {EFFORT_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </Select>
    </div>
  );
}
