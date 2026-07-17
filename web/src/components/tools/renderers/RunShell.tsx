import { ToolCallCard, ResultSection } from "../ToolCallCard";
import type { ToolRenderProps } from "../types";

/**
 * run_shell: the command reads like a prompt line, and the combined
 * stdout/stderr output renders in a terminal-styled block — dark in both
 * themes, the way shell output is expected to look.
 */
export function RunShellRenderer({ name, args, result, status }: ToolRenderProps) {
  const command = typeof args.command === "string" ? args.command : "";

  return (
    <ToolCallCard name={name} status={status} subtitle={`$ ${command}`}>
      {/* The terminal token group, finally spent. Dark in both modes today —
          but that is now the theme's decision rather than a zinc/emerald
          palette hardcoded where no theme could reach it. */}
      <div className="rounded-ctl overflow-hidden bg-app-terminal-bg border border-app-terminal-border">
        <div className="px-3 py-2 font-mono text-xs text-app-terminal-muted border-b border-app-terminal-border whitespace-pre-wrap break-words">
          <span className="text-app-terminal-accent select-none">$ </span>
          {command}
        </div>
        {typeof result === "string" && status !== "error" && (
          <pre className="p-3 font-mono text-[0.8rem] text-app-terminal-fg overflow-x-auto max-h-80 overflow-y-auto whitespace-pre-wrap break-words">
            {result}
          </pre>
        )}
        {result === undefined && status === "running" && (
          <div className="p-3 font-mono text-xs text-app-terminal-dim">running…</div>
        )}
      </div>
      {status === "error" && <ResultSection result={result} status={status} />}
    </ToolCallCard>
  );
}
