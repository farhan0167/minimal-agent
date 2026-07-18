import { ToolCallCard, ResultSection } from "../ToolCallCard";
import type { ToolRenderProps } from "../types";

/**
 * web_search results arrive pre-formatted by the backend
 * (web_search/tool.py render_result_for_assistant):
 *
 *   **Answer:** <optional LLM answer>
 *   [1] <title>
 *       <url>
 *       <content snippet>
 *
 * Parse that into linked result cards with favicons; anything that doesn't
 * match the format falls back to raw text.
 */
interface SearchHit {
  title: string;
  url: string;
  snippet: string;
}

function parseSearchResult(result: string): {
  answer: string | null;
  hits: SearchHit[];
} | null {
  const lines = result.split("\n");
  const hits: SearchHit[] = [];
  let answer: string | null = null;
  let current: SearchHit | null = null;

  for (const line of lines) {
    const startMatch = /^\[\d+\] (.*)$/.exec(line);
    if (startMatch) {
      if (current) hits.push(current);
      current = { title: startMatch[1], url: "", snippet: "" };
      continue;
    }
    if (current) {
      const text = line.trim();
      // Raw page content (include_raw_content) is too long for a card.
      if (text.startsWith("--- Full content ---")) {
        hits.push(current);
        current = null;
        continue;
      }
      if (!current.url && /^https?:\/\//.test(text)) {
        current.url = text;
      } else if (text) {
        current.snippet = current.snippet ? `${current.snippet} ${text}` : text;
      }
    } else if (line.startsWith("**Answer:**")) {
      answer = line.slice("**Answer:**".length).trim();
    }
  }
  if (current) hits.push(current);

  return hits.length > 0 ? { answer, hits } : null;
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

export function WebSearchRenderer({ name, args, result, status }: ToolRenderProps) {
  const query = typeof args.query === "string" ? args.query : "";
  const parsed =
    status !== "error" && typeof result === "string"
      ? parseSearchResult(result)
      : null;

  return (
    <ToolCallCard name={name} status={status} subtitle={`“${query}”`}>
      <ResultSection result={result} status={status}>
        {parsed ? (
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {parsed.answer && (
              <p className="text-sm text-app-fg bg-app-hover p-3 rounded-ctl">
                {parsed.answer}
              </p>
            )}
            {parsed.hits.map((hit, i) => {
              const host = hostOf(hit.url);
              return (
                <div
                  key={i}
                  className="p-3 rounded-ctl border border-app-border bg-app-hover"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    {host && (
                      <img
                        src={`https://www.google.com/s2/favicons?domain=${host}&sz=32`}
                        alt=""
                        loading="lazy"
                        className="w-4 h-4 shrink-0 rounded-sm"
                        onError={(e) => {
                          e.currentTarget.style.display = "none";
                        }}
                      />
                    )}
                    <a
                      href={hit.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm font-medium truncate text-app-accent hover:underline"
                    >
                      {hit.title || hit.url}
                    </a>
                  </div>
                  {host && (
                    <div className="text-xs text-app-fg-muted mt-0.5 truncate">
                      {host}
                    </div>
                  )}
                  {hit.snippet && (
                    <p className="text-xs text-app-fg-muted mt-1 line-clamp-2">
                      {hit.snippet}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        ) : undefined}
      </ResultSection>
    </ToolCallCard>
  );
}
