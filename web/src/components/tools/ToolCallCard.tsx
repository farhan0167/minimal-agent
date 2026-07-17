import { useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight, CircleAlert, Loader2 } from "lucide-react";
import { Badge } from "../ui/Badge";

export type ToolStatus = "running" | "complete" | "error" | "interrupted";

interface ToolCallCardProps {
  name: string;
  status: ToolStatus;
  /** Muted, truncated context shown next to the tool name (path, command, query…). */
  subtitle?: ReactNode;
  /** Expanded body. */
  children: ReactNode;
}

/**
 * Shared collapsible shell for tool-call cards: header with tool name,
 * per-tool subtitle and status badge; body revealed on click.
 *
 * Per-tool renderers compose this with their own body; ToolCallRenderer
 * is the generic fallback.
 */
export function ToolCallCard({
  name,
  status,
  subtitle,
  children,
}: ToolCallCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="my-2 border border-[hsl(var(--claude-border))] rounded-lg overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 w-full px-4 py-2.5 bg-[hsl(var(--claude-hover))] hover:bg-[hsl(var(--claude-active))] transition-colors text-left"
      >
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 shrink-0 text-[hsl(var(--aui-muted-foreground))]" />
        ) : (
          <ChevronRight className="w-4 h-4 shrink-0 text-[hsl(var(--aui-muted-foreground))]" />
        )}
        <span className="font-mono text-sm font-medium shrink-0 text-[hsl(var(--aui-foreground))]">
          {name}
        </span>
        {subtitle && (
          <span className="min-w-0 truncate font-mono text-xs text-[hsl(var(--aui-muted-foreground))]">
            {subtitle}
          </span>
        )}
        {status === "running" && (
          <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin text-[hsl(var(--aui-primary))]" />
        )}
        {status === "error" && (
          <Badge variant="danger">
            <CircleAlert className="w-3 h-3" />
            failed
          </Badge>
        )}
        {status === "interrupted" && (
          <Badge variant="neutral">interrupted</Badge>
        )}
      </button>

      {isExpanded && <div className="px-4 py-3 space-y-3">{children}</div>}
    </div>
  );
}

/** Small muted label above a section of the card body. */
export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="text-xs font-medium text-[hsl(var(--aui-muted-foreground))] mb-1">
      {children}
    </div>
  );
}

/** Pretty-printed args JSON, the default "Args" section. */
export function ArgsSection({ args }: { args: Record<string, unknown> }) {
  return (
    <div>
      <SectionLabel>Args</SectionLabel>
      <pre className="text-sm bg-[hsl(var(--claude-hover))] p-3 rounded-lg overflow-x-auto font-mono">
        {JSON.stringify(args, null, 2)}
      </pre>
    </div>
  );
}

/** Raw result in a scroll-capped pre; red-tinted when the tool failed. */
export function RawResult({
  result,
  isError,
}: {
  result: unknown;
  isError?: boolean;
}) {
  return (
    <pre
      className={`text-sm p-3 rounded-lg overflow-x-auto max-h-64 overflow-y-auto font-mono whitespace-pre-wrap break-words ${
        isError
          ? "bg-[hsl(var(--aui-destructive)/0.08)] text-[hsl(var(--aui-destructive))] border border-[hsl(var(--aui-destructive)/0.25)]"
          : "bg-[hsl(var(--claude-hover))]"
      }`}
    >
      {typeof result === "string" ? result : JSON.stringify(result, null, 2)}
    </pre>
  );
}

interface ResultSectionProps {
  result: unknown;
  status: ToolStatus;
  /** Rich rendering of a successful result; ignored on error. */
  children?: ReactNode;
}

/**
 * The "Result" section of a card body. Failed results always render as the
 * raw red-tinted error text — per-tool parsers only see success output.
 * While the tool is still running there is nothing to show.
 */
export function ResultSection({ result, status, children }: ResultSectionProps) {
  if (result === undefined) return null;
  const isError = status === "error";
  return (
    <div>
      <SectionLabel>Result</SectionLabel>
      {isError || children === undefined ? (
        <RawResult result={result} isError={isError} />
      ) : (
        children
      )}
    </div>
  );
}
