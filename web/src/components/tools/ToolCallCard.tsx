import { type ReactNode } from "react";
import { CircleAlert } from "lucide-react";
import { Badge } from "../ui/Badge";
import { Surface } from "../ui/Surface";
import { Text } from "../ui/Text";
import { Disclosure } from "../ui/Disclosure";
import { Spinner } from "../ui/Spinner";
import { StatusDot } from "../ui/StatusDot";

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
  return (
    <Surface variant="outline" className="my-2">
      <Disclosure
        summary={
          <>
            <span className="font-mono text-sm font-medium shrink-0 text-app-fg">
              {name}
            </span>
            {subtitle && (
              <Text variant="code" as="span" className="min-w-0 truncate">
                {subtitle}
              </Text>
            )}
            {status === "running" && <Spinner />}
            {status === "error" && (
              <Badge variant="danger">
                <CircleAlert className="w-3 h-3" />
                failed
              </Badge>
            )}
            {status === "interrupted" && (
              <Badge variant="neutral">
                <StatusDot status="interrupted" />
                interrupted
              </Badge>
            )}
          </>
        }
      >
        <div className="px-4 py-3 space-y-3">{children}</div>
      </Disclosure>
    </Surface>
  );
}

/** Small muted label above a section of the card body. */
export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <Text variant="label" as="div" muted className="mb-1">
      {children}
    </Text>
  );
}

/** Pretty-printed args JSON, the default "Args" section. */
export function ArgsSection({ args }: { args: Record<string, unknown> }) {
  return (
    <div>
      <SectionLabel>Args</SectionLabel>
      <Surface variant="inset" className="p-3 overflow-x-auto">
        <pre className="text-sm font-mono">{JSON.stringify(args, null, 2)}</pre>
      </Surface>
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
  // The error ground is a semantic tint rather than a Surface variant: it says
  // "this failed", not "this is a container", and only --app-danger can say it.
  return (
    <pre
      className={`text-sm p-3 rounded-ctl overflow-x-auto max-h-64 overflow-y-auto font-mono whitespace-pre-wrap break-words ${
        isError
          ? "bg-app-danger/10 text-app-danger border border-app-danger/20"
          : "bg-app-hover"
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
