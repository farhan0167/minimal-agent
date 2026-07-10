import { useCallback, useState, type FC } from "react";
import DOMPurify from "dompurify";
import { CodeIcon, ImageIcon, Maximize2Icon } from "lucide-react";
import type {
  CodeHeaderProps,
  SyntaxHighlighterProps,
} from "@assistant-ui/react-markdown";
import { ShikiSyntaxHighlighter } from "../chat/ShikiHighlighter";
import { CodeHeaderBar, HeaderButton } from "./CodeHeaderBar";
import { PreviewDialog, ZoomControls, ZoomPane } from "./PreviewDialog";
import { useZoom } from "./use-zoom";

const MAX_SVG_BYTES = 256 * 1024;

/**
 * Sanitize SVG markup for inline rendering. Returns null when the markup is
 * oversized or nothing survives sanitization (then we show source instead).
 */
function sanitizeSvg(code: string): string | null {
  if (code.length > MAX_SVG_BYTES) return null;
  const clean = DOMPurify.sanitize(code, {
    USE_PROFILES: { svg: true, svgFilters: true },
    FORBID_TAGS: ["foreignObject", "script"],
  });
  return clean.trim() ? clean : null;
}

const isAbsoluteLength = (v: string | null): v is string =>
  !!v && /^\d+(\.\d+)?(px)?$/.test(v.trim());

/**
 * Model-generated SVGs often size themselves with width/height="100%" and no
 * viewBox, which stretches the element to the container while the artwork
 * stays in fixed user units — stray shapes render outside the intended
 * canvas. Give every SVG a viewBox (from its width/height attributes, else
 * by measuring the drawing) and let CSS scale it, so it frames and clips
 * like an image.
 */
function normalizeSvg(root: ShadowRoot) {
  const svg = root.querySelector("svg");
  if (!svg) return;

  const width = svg.getAttribute("width");
  const height = svg.getAttribute("height");

  if (!svg.hasAttribute("viewBox")) {
    if (isAbsoluteLength(width) && isAbsoluteLength(height)) {
      svg.setAttribute("viewBox", `0 0 ${parseFloat(width)} ${parseFloat(height)}`);
    } else {
      try {
        const box = svg.getBBox();
        if (box.width > 0 && box.height > 0) {
          svg.setAttribute(
            "viewBox",
            `${box.x} ${box.y} ${box.width} ${box.height}`,
          );
        }
      } catch {
        // getBBox can throw for degenerate content — leave the SVG as is.
      }
    }
  }

  // Relative sizing (width="100%") has nothing meaningful to resolve
  // against here. Give the svg intrinsic dimensions from its viewBox so the
  // host CSS can scale it down to fit the card, exactly like an <img>.
  if (!isAbsoluteLength(width) || !isAbsoluteLength(height)) {
    const vb = svg.viewBox.baseVal;
    if (vb && vb.width > 0 && vb.height > 0) {
      svg.setAttribute("width", String(vb.width));
      svg.setAttribute("height", String(vb.height));
    } else {
      // No viewBox could be derived — fall back to the browser default size.
      svg.removeAttribute("width");
      svg.removeAttribute("height");
    }
  }
}

// "card": scale down to fit the chat card (max-width/max-height with auto
// dimensions keeps the aspect ratio, like an image) — always fully visible.
// "natural": intrinsic size, for the preview dialog where a ZoomPane owns
// scaling and scrolling.
const SHADOW_STYLE = {
  card: ":host{display:block}svg{display:block;margin:auto;width:auto;height:auto;max-width:100%;max-height:min(24rem,55vh);overflow:hidden}",
  natural: ":host{display:block}svg{display:block;margin:auto;overflow:hidden}",
} as const;

/**
 * Mount sanitized markup inside a shadow root so the SVG's ids, classes and
 * <style> rules can't collide with (or restyle) the app.
 */
function ShadowSvg({
  markup,
  fit = "card",
}: {
  markup: string;
  fit?: keyof typeof SHADOW_STYLE;
}) {
  const ref = useCallback(
    (node: HTMLDivElement | null) => {
      if (!node) return;
      const root = node.shadowRoot ?? node.attachShadow({ mode: "open" });
      root.innerHTML = `<style>${SHADOW_STYLE[fit]}</style>${markup}`;
      normalizeSvg(root);
    },
    [markup, fit],
  );
  return (
    <div ref={ref} className={fit === "card" ? "p-4 bg-white rounded-b-lg" : ""} />
  );
}

function SvgPreviewDialog({
  markup,
  onClose,
}: {
  markup: string;
  onClose: () => void;
}) {
  const zoom = useZoom();
  return (
    <PreviewDialog
      title="SVG preview"
      controls={<ZoomControls {...zoom} />}
      onClose={onClose}
    >
      <ZoomPane zoom={zoom.zoom} zoomBy={zoom.zoomBy} className="bg-white">
        <ShadowSvg markup={markup} fit="natural" />
      </ZoomPane>
    </PreviewDialog>
  );
}

/**
 * SvgBlock renders its own header (language label, rendered/source toggle,
 * copy), so the default CodeHeader must be suppressed for svg/xml fences —
 * register this alongside it in componentsByLanguage.
 */
export const NullCodeHeader: FC<CodeHeaderProps> = () => null;

/**
 * Renderer for `svg` and `xml` fences. Complete SVG documents render live
 * (sanitized, in a shadow root) with a rendered/source toggle in the header;
 * while the fence is still streaming (no closing </svg> yet) and for non-SVG
 * XML, the body falls through to the normal Shiki view.
 */
export const SvgBlock: FC<SyntaxHighlighterProps> = (props) => {
  const { code, language } = props;
  const [showSource, setShowSource] = useState(false);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);

  const isCompleteSvg = /<svg[\s>]/i.test(code) && /<\/svg>/i.test(code);
  const sanitized = isCompleteSvg ? sanitizeSvg(code) : null;
  const showRendered = sanitized !== null && !showSource;

  return (
    <div>
      <CodeHeaderBar language={language} code={code}>
        {sanitized !== null && (
          <>
            <HeaderButton
              onClick={() => setIsPreviewOpen(true)}
              title="Enlarge in a zoomable preview"
            >
              <Maximize2Icon className="w-3.5 h-3.5" />
              Preview
            </HeaderButton>
            <HeaderButton
              onClick={() => setShowSource(!showSource)}
              title={showSource ? "Show rendered SVG" : "Show source"}
            >
              {showSource ? (
                <>
                  <ImageIcon className="w-3.5 h-3.5" />
                  Rendered
                </>
              ) : (
                <>
                  <CodeIcon className="w-3.5 h-3.5" />
                  Source
                </>
              )}
            </HeaderButton>
          </>
        )}
      </CodeHeaderBar>
      {showRendered ? (
        <ShadowSvg markup={sanitized} />
      ) : (
        <ShikiSyntaxHighlighter {...props} language="xml" />
      )}
      {isPreviewOpen && sanitized !== null && (
        <SvgPreviewDialog
          markup={sanitized}
          onClose={() => setIsPreviewOpen(false)}
        />
      )}
    </div>
  );
};
