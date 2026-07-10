import { useEffect, useState, type FC } from "react";
import { Maximize2Icon } from "lucide-react";
import { useMessagePartText } from "@assistant-ui/react";
import type { SyntaxHighlighterProps } from "@assistant-ui/react-markdown";
import { ShikiSyntaxHighlighter } from "../chat/ShikiHighlighter";
import { useIsDark } from "../../hooks/use-is-dark";
import { CodeHeaderBar, HeaderButton } from "./CodeHeaderBar";
import { PreviewDialog, ZoomControls, ZoomPane } from "./PreviewDialog";
import { useZoom } from "./use-zoom";

// Mermaid is ~1.5 MB, so it loads on the first diagram, not at startup.
let mermaidPromise: Promise<typeof import("mermaid").default> | null = null;
function getMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import("mermaid").then((m) => m.default);
  }
  return mermaidPromise;
}

let renderSeq = 0;

function MermaidPreviewDialog({
  svg,
  onClose,
}: {
  svg: string;
  onClose: () => void;
}) {
  const zoom = useZoom();
  return (
    <PreviewDialog
      title="Mermaid preview"
      controls={<ZoomControls {...zoom} />}
      onClose={onClose}
    >
      <ZoomPane
        zoom={zoom.zoom}
        zoomBy={zoom.zoomBy}
        className="bg-[hsl(var(--aui-background))]"
      >
        <div dangerouslySetInnerHTML={{ __html: svg }} />
      </ZoomPane>
    </PreviewDialog>
  );
}

/**
 * Renderer for `mermaid` fences. While the message is still streaming it
 * shows a quiet placeholder (partial diagrams rarely parse); once complete
 * it validates and renders the diagram, falling back to highlighted source
 * if mermaid rejects it. Renders its own header (register NullCodeHeader
 * alongside it) so the Preview button can open the diagram in a zoomable
 * dialog.
 */
export const MermaidBlock: FC<SyntaxHighlighterProps> = (props) => {
  const { code, language } = props;
  const isDark = useIsDark();
  const { status } = useMessagePartText();
  const isStreaming = status.type === "running";

  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);

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

  let body;
  if (svg) {
    body = (
      <div
        className="p-4 flex justify-center bg-[hsl(var(--claude-code-bg))] rounded-b-lg max-h-[min(26rem,60vh)] overflow-auto"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    );
  } else if (isStreaming || !failed) {
    body = (
      <div className="p-4 text-xs animate-pulse text-[hsl(var(--aui-muted-foreground))] bg-[hsl(var(--claude-code-bg))] rounded-b-lg">
        Generating diagram…
      </div>
    );
  } else {
    // Invalid diagram — keep the source visible rather than hiding the block.
    body = (
      <div>
        <div className="px-4 py-1.5 text-xs text-[hsl(var(--aui-muted-foreground))] bg-[hsl(var(--claude-code-bg))]">
          Mermaid couldn't render this diagram — showing source.
        </div>
        <ShikiSyntaxHighlighter {...props} language="text" />
      </div>
    );
  }

  return (
    <div>
      <CodeHeaderBar language={language} code={code}>
        {svg !== null && (
          <HeaderButton
            onClick={() => setIsPreviewOpen(true)}
            title="Enlarge in a zoomable preview"
          >
            <Maximize2Icon className="w-3.5 h-3.5" />
            Preview
          </HeaderButton>
        )}
      </CodeHeaderBar>
      {body}
      {isPreviewOpen && svg !== null && (
        <MermaidPreviewDialog
          svg={svg}
          onClose={() => setIsPreviewOpen(false)}
        />
      )}
    </div>
  );
};
