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
      <div className="rounded-lg overflow-hidden bg-zinc-900 border border-zinc-800">
        <div className="px-3 py-2 font-mono text-xs text-zinc-400 border-b border-zinc-800 whitespace-pre-wrap break-words">
          <span className="text-emerald-400 select-none">$ </span>
          {command}
        </div>
        {typeof result === "string" && status !== "error" && (
          <pre className="p-3 font-mono text-[0.8rem] text-zinc-100 overflow-x-auto max-h-80 overflow-y-auto whitespace-pre-wrap break-words">
            {result}
          </pre>
        )}
        {result === undefined && status === "running" && (
          <div className="p-3 font-mono text-xs text-zinc-500">running…</div>
        )}
      </div>
      {status === "error" && <ResultSection result={result} status={status} />}
    </ToolCallCard>
  );
}
