import { ToolCallCard, ResultSection, SectionLabel } from "../ToolCallCard";
import { CodeBlock } from "../CodeBlock";
import { languageForPath } from "../../../lib/code-language";
import type { ToolRenderProps } from "../types";

/**
 * write_file: the interesting payload is in the args (the content being
 * written), so show it highlighted even while the tool is still running.
 * The result is just a one-line confirmation ("Created /path (N lines)").
 */
export function WriteFileRenderer({ name, args, result, status }: ToolRenderProps) {
  const filePath = typeof args.file_path === "string" ? args.file_path : "";
  const content = typeof args.content === "string" ? args.content : null;

  return (
    <ToolCallCard name={name} status={status} subtitle={filePath}>
      {content !== null && (
        <div>
          <SectionLabel>Content</SectionLabel>
          <CodeBlock code={content} language={languageForPath(filePath)} />
        </div>
      )}
      {status === "error" ? (
        <ResultSection result={result} status={status} />
      ) : (
        typeof result === "string" && (
          <div className="text-xs text-app-fg-muted">
            {result}
          </div>
        )
      )}
    </ToolCallCard>
  );
}
