import { useRef, useState, type FC } from "react";
import { PlayIcon } from "lucide-react";
import type { CodeHeaderProps } from "@assistant-ui/react-markdown";
import { CodeHeaderBar, HeaderButton } from "./CodeHeaderBar";
import { PreviewDialog, ZoomControls } from "./PreviewDialog";
import { useWheelZoom, useZoom } from "./use-zoom";

/**
 * Code-block header for `html` fences: the standard language label + copy
 * button, plus a Preview button that opens the markup in a sandboxed iframe.
 *
 * Security posture (matching llama.cpp's webui): `allow-scripts` only, never
 * `allow-same-origin` — the combination would let previewed content reach
 * this origin's storage and APIs. The iframe unmounts (and srcDoc with it)
 * when the dialog closes.
 */
export const HtmlCodeHeader: FC<CodeHeaderProps> = ({ language, code }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <CodeHeaderBar language={language} code={code}>
        <HeaderButton
          onClick={() => setIsOpen(true)}
          title="Preview HTML in a sandboxed frame"
        >
          <PlayIcon className="w-3.5 h-3.5" />
          Preview
        </HeaderButton>
      </CodeHeaderBar>
      {isOpen && (
        <HtmlPreviewDialog code={code} onClose={() => setIsOpen(false)} />
      )}
    </>
  );
};

function HtmlPreviewDialog({
  code,
  onClose,
}: {
  code: string;
  onClose: () => void;
}) {
  const zoom = useZoom();
  const paneRef = useRef<HTMLDivElement>(null);
  // Catches ctrl/meta+wheel over the dialog chrome; wheel events over the
  // iframe itself go to the sandboxed document and can't be intercepted —
  // the header buttons always work.
  useWheelZoom(paneRef, zoom.zoomBy);

  return (
    <PreviewDialog
      title="HTML preview"
      controls={<ZoomControls {...zoom} />}
      onClose={onClose}
    >
      <div ref={paneRef} className="flex-1 overflow-hidden bg-white">
        {/* Scale + inverse size emulates browser zoom: zooming out gives the
            page a wider viewport to lay out in, like a real zoomed browser. */}
        <iframe
          sandbox="allow-scripts"
          srcDoc={code}
          title="HTML preview"
          className="border-0 bg-white"
          style={{
            transform: `scale(${zoom.zoom})`,
            transformOrigin: "0 0",
            width: `${100 / zoom.zoom}%`,
            height: `${100 / zoom.zoom}%`,
          }}
        />
      </div>
    </PreviewDialog>
  );
}
