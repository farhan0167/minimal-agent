import { ToolCallCard, ResultSection } from "../ToolCallCard";
import type { ToolRenderProps } from "../types";

/**
 * grep and glob: both take a `pattern` arg and return line-oriented text —
 * file lists ("Found N files" + paths, or bare paths from glob) or
 * path:line:content matches from grep's content mode. A leading summary line
 * ("Found 3 files", "No files found") is lifted out as a caption; the rest
 * renders as a monospace list.
 */
const SUMMARY_LINE = /^(Found \d+ files?|No files found|No matches found)$/;

export function SearchRenderer({ name, args, result, status }: ToolRenderProps) {
  const pattern = typeof args.pattern === "string" ? args.pattern : "";
  const path = typeof args.path === "string" ? args.path : null;
  const subtitle = path ? `${pattern} in ${path}` : pattern;

  let caption: string | null = null;
  let lines: string[] = [];
  if (typeof result === "string" && status !== "error") {
    lines = result.split("\n");
    if (lines.length > 0 && SUMMARY_LINE.test(lines[0])) {
      caption = lines[0];
      lines = lines.slice(1);
    }
    lines = lines.filter((line) => line.length > 0);
  }

  return (
    <ToolCallCard name={name} status={status} subtitle={subtitle}>
      <ResultSection result={result} status={status}>
        {typeof result === "string" ? (
          <div>
            {caption && (
              <div className="text-xs text-app-fg-muted mb-1.5">
                {caption}
              </div>
            )}
            {lines.length > 0 && (
              <ul className="text-[0.8rem] font-mono bg-app-hover p-3 rounded-ctl overflow-x-auto max-h-80 overflow-y-auto">
                {lines.map((line, i) => (
                  <li key={i} className="whitespace-pre">
                    {line}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : undefined}
      </ResultSection>
    </ToolCallCard>
  );
}
