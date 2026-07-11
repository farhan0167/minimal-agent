import type { ReasoningEffort } from "../../api/chat";
import type { ReasoningState } from "../../hooks/use-chat-runtime";

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
 * Phase-one placement is a small toolbar above the prebuilt <Thread> — the
 * prebuilt composer has no slot for extra controls, and inlining it there
 * would require a custom ComposerPrimitive. The state lives in ChatPanel and
 * is read by the runtime adapter at send time (see use-chat-runtime).
 */
export function ReasoningControls({ value, onChange }: ReasoningControlsProps) {
  const { on, effort } = value;

  return (
    <div className="flex items-center gap-3 px-4 py-2 text-xs text-[hsl(var(--aui-muted-foreground))]">
      <button
        type="button"
        role="switch"
        aria-checked={on}
        onClick={() => onChange({ ...value, on: !on })}
        className="flex items-center gap-2 hover:text-[hsl(var(--aui-foreground))] transition-colors"
      >
        <span
          aria-hidden
          className="relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors"
          style={{
            backgroundColor: on
              ? "hsl(var(--aui-primary))"
              : "hsl(var(--aui-border))",
          }}
        >
          <span
            className="inline-block h-3 w-3 rounded-full bg-white transition-transform"
            style={{ transform: on ? "translateX(14px)" : "translateX(2px)" }}
          />
        </span>
        <span className="font-medium">Thinking</span>
      </button>

      <label
        className={`flex items-center gap-1.5 transition-opacity ${
          on ? "opacity-100" : "opacity-40"
        }`}
      >
        <span>Effort</span>
        <select
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
          className="rounded border border-[hsl(var(--aui-border))] bg-transparent px-1.5 py-0.5 text-xs text-[hsl(var(--aui-foreground))] disabled:cursor-not-allowed focus:outline-none focus:ring-1 focus:ring-[hsl(var(--aui-primary))]"
        >
          {EFFORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
