import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

interface ToolCallRendererProps {
  name: string;
  args: Record<string, unknown>;
  result: unknown;
  status: "running" | "complete" | "error";
}

export function ToolCallRenderer({
  name,
  args,
  result,
  status,
}: ToolCallRendererProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="my-2 border border-[hsl(var(--claude-border))] rounded-lg overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 w-full px-4 py-2.5 bg-[hsl(var(--claude-hover))] hover:bg-[hsl(var(--claude-active))] transition-colors text-left"
      >
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-[hsl(var(--aui-muted-foreground))]" />
        ) : (
          <ChevronRight className="w-4 h-4 text-[hsl(var(--aui-muted-foreground))]" />
        )}
        <span className="font-mono text-sm font-medium text-[hsl(var(--aui-foreground))]">
          {name}
        </span>
        {status === "running" && (
          <span className="ml-auto text-sm text-[hsl(var(--aui-primary))] animate-pulse">
            running...
          </span>
        )}
        {status === "error" && (
          <span className="ml-auto text-sm text-[hsl(var(--aui-destructive))]">error</span>
        )}
      </button>

      {isExpanded && (
        <div className="px-4 py-3 space-y-3">
          <div>
            <div className="text-xs font-medium text-[hsl(var(--aui-muted-foreground))] mb-1">Args</div>
            <pre className="text-sm bg-[hsl(var(--claude-hover))] p-3 rounded-lg overflow-x-auto font-mono">
              {JSON.stringify(args, null, 2)}
            </pre>
          </div>
          {result !== undefined && (
            <div>
              <div className="text-xs font-medium text-[hsl(var(--aui-muted-foreground))] mb-1">
                Result
              </div>
              <pre className="text-sm bg-[hsl(var(--claude-hover))] p-3 rounded-lg overflow-x-auto max-h-64 overflow-y-auto font-mono">
                {typeof result === "string"
                  ? result
                  : JSON.stringify(result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
