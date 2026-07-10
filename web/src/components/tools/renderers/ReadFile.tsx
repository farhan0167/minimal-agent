import { ToolCallCard, ResultSection, SectionLabel } from "../ToolCallCard";
import { CodeBlock } from "../CodeBlock";
import { languageForPath } from "../../../lib/code-language";
import type { ToolRenderProps } from "../types";

/**
 * read_file results arrive as a "Lines X-Y of Z total" header followed by
 * cat -n numbered lines (see read_file/helpers.py). Strip the numbering and
 * highlight the code by file extension. Image/PDF reads (a plain pointer
 * sentence) and anything else unrecognized fall back to raw text.
 */
function parseReadResult(result: string) {
  const nl = result.indexOf("\n");
  const header = nl === -1 ? result : result.slice(0, nl);
  if (!/^Lines \d+-\d+ of \d+ total$/.test(header)) return null;
  const body = nl === -1 ? "" : result.slice(nl + 1);
  const code = body
    .split("\n")
    .map((line) => line.replace(/^\s*\d+\t/, ""))
    .join("\n");
  return { header, code };
}

export function ReadFileRenderer({ name, args, result, status }: ToolRenderProps) {
  const filePath = typeof args.file_path === "string" ? args.file_path : "";
  const parsed =
    status !== "error" && typeof result === "string"
      ? parseReadResult(result)
      : null;

  return (
    <ToolCallCard name={name} status={status} subtitle={filePath}>
      <ResultSection result={result} status={status}>
        {parsed ? (
          <div>
            <div className="text-xs text-[hsl(var(--aui-muted-foreground))] mb-1.5">
              {parsed.header}
            </div>
            <CodeBlock code={parsed.code} language={languageForPath(filePath)} />
          </div>
        ) : undefined}
      </ResultSection>
      {result === undefined && <SectionLabel>Reading…</SectionLabel>}
    </ToolCallCard>
  );
}
