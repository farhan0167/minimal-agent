import { ToolCallCard, ResultSection } from "../ToolCallCard";
import { ToolMarkdown } from "../ToolMarkdown";
import type { ToolRenderProps } from "../types";

/**
 * web_extract results arrive as markdown-ish sections
 * (web_extract/tool.py render_result_for_assistant):
 *
 *   ## <url>
 *   <extracted page content, markdown by default>
 *   FAILED: <url> — <error>
 *
 * Split on the `## url` headers, link each URL, and render the extracted
 * content through markdown. Unparseable results fall back to raw text.
 */
interface ExtractSection {
  url: string;
  content: string;
}

function parseExtractResult(result: string): {
  sections: ExtractSection[];
  failures: string[];
} | null {
  const sections: ExtractSection[] = [];
  const failures: string[] = [];
  let current: ExtractSection | null = null;

  for (const line of result.split("\n")) {
    const header = /^## (https?:\/\/\S+)$/.exec(line);
    if (header) {
      if (current) sections.push(current);
      current = { url: header[1], content: "" };
      continue;
    }
    if (line.startsWith("FAILED: ")) {
      if (current) {
        sections.push(current);
        current = null;
      }
      failures.push(line.slice("FAILED: ".length));
      continue;
    }
    if (current) current.content += (current.content ? "\n" : "") + line;
  }
  if (current) sections.push(current);

  return sections.length > 0 || failures.length > 0
    ? { sections, failures }
    : null;
}

export function WebExtractRenderer({ name, args, result, status }: ToolRenderProps) {
  const urls = Array.isArray(args.urls) ? (args.urls as string[]) : [];
  const subtitle = urls.length === 1 ? urls[0] : `${urls.length} URLs`;
  const parsed =
    status !== "error" && typeof result === "string"
      ? parseExtractResult(result)
      : null;

  return (
    <ToolCallCard name={name} status={status} subtitle={subtitle}>
      <ResultSection result={result} status={status}>
        {parsed ? (
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {parsed.sections.map((section, i) => (
              <div key={i}>
                <a
                  href={section.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block text-sm font-medium mb-1 truncate text-app-accent hover:underline"
                >
                  {section.url}
                </a>
                <ToolMarkdown text={section.content.trim()} />
              </div>
            ))}
            {parsed.failures.map((failure, i) => (
              <div
                key={i}
                className="text-xs p-2 rounded-ctl bg-app-danger/10 text-app-danger"
              >
                {failure}
              </div>
            ))}
          </div>
        ) : undefined}
      </ResultSection>
    </ToolCallCard>
  );
}
