import { useEffect, useState, type FC } from "react";
import { useMessagePartText } from "@assistant-ui/react";
import type { SyntaxHighlighterProps } from "@assistant-ui/react-markdown";
import { ShikiSyntaxHighlighter } from "../chat/ShikiHighlighter";
import { useIsDark } from "../../hooks/use-is-dark";

// Mermaid is ~1.5 MB, so it loads on the first diagram, not at startup.
let mermaidPromise: Promise<typeof import("mermaid").default> | null = null;
function getMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import("mermaid").then((m) => m.default);
  }
  return mermaidPromise;
}

let renderSeq = 0;

/**
 * Renderer for `mermaid` fences. While the message is still streaming it
 * shows a quiet placeholder (partial diagrams rarely parse); once complete
 * it validates and renders the diagram, falling back to highlighted source
 * if mermaid rejects it.
 */
export const MermaidBlock: FC<SyntaxHighlighterProps> = (props) => {
  const { code } = props;
  const isDark = useIsDark();
  const { status } = useMessagePartText();
  const isStreaming = status.type === "running";

  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (isStreaming) return;
    let cancelled = false;

    (async () => {
      try {
        const mermaid = await getMermaid();
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: isDark ? "dark" : "default",
        });
        // parse() first: it reports invalid input without mermaid.render's
        // side effect of appending an error element to <body>.
        const ok = await mermaid.parse(code, { suppressErrors: true });
        if (!ok) {
          if (!cancelled) setFailed(true);
          return;
        }
        const { svg: rendered } = await mermaid.render(
          `mermaid-block-${++renderSeq}`,
          code,
        );
        if (!cancelled) {
          setSvg(rendered);
          setFailed(false);
        }
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [code, isDark, isStreaming]);

  if (svg) {
    return (
      <div
        className="p-4 flex justify-center bg-[hsl(var(--claude-code-bg))] rounded-b-lg max-h-[min(26rem,60vh)] overflow-auto"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    );
  }

  if (isStreaming || (!failed && !svg)) {
    return (
      <div className="p-4 text-xs animate-pulse text-[hsl(var(--aui-muted-foreground))] bg-[hsl(var(--claude-code-bg))] rounded-b-lg">
        Generating diagram…
      </div>
    );
  }

  // Invalid diagram — keep the source visible rather than hiding the block.
  return (
    <div>
      <div className="px-4 py-1.5 text-xs text-[hsl(var(--aui-muted-foreground))] bg-[hsl(var(--claude-code-bg))]">
        Mermaid couldn't render this diagram — showing source.
      </div>
      <ShikiSyntaxHighlighter {...props} language="text" />
    </div>
  );
};
