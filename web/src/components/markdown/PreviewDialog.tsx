import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { MinusIcon, PlusIcon, XIcon } from "lucide-react";
import { useWheelZoom, type Zoom } from "./use-zoom";

const zoomButtonClass =
  "p-1.5 rounded hover:bg-[hsl(var(--claude-hover))] transition-colors";

export function ZoomControls({ zoom, zoomBy, reset }: Zoom) {
  return (
    <div className="flex items-center font-sans text-[hsl(var(--aui-foreground))]">
      <button
        onClick={() => zoomBy(1 / 1.25)}
        className={zoomButtonClass}
        title="Zoom out"
      >
        <MinusIcon className="w-4 h-4" />
      </button>
      <button
        onClick={reset}
        className="w-12 py-1 text-xs text-center tabular-nums rounded hover:bg-[hsl(var(--claude-hover))] transition-colors"
        title="Reset zoom"
      >
        {Math.round(zoom * 100)}%
      </button>
      <button
        onClick={() => zoomBy(1.25)}
        className={zoomButtonClass}
        title="Zoom in"
      >
        <PlusIcon className="w-4 h-4" />
      </button>
    </div>
  );
}

/**
 * Scrollable dialog body whose content is scaled by `zoom`. CSS zoom (unlike
 * transform: scale) is layout-aware, so the scroll range tracks the scaled
 * size. Content centers when smaller than the pane.
 */
export function ZoomPane({
  zoom,
  zoomBy,
  className,
  children,
}: {
  zoom: number;
  zoomBy: Zoom["zoomBy"];
  className?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useWheelZoom(ref, zoomBy);
  return (
    <div ref={ref} className={`flex-1 overflow-auto p-4 ${className ?? ""}`}>
      <div className="w-fit mx-auto" style={{ zoom }}>
        {children}
      </div>
    </div>
  );
}

/**
 * Shared modal chrome for rich-content previews (HTML, SVG, Mermaid):
 * dimmed overlay, titled header with optional controls (zoom), close on
 * Esc / overlay click / the X button. Portal-mounted so the chat's serif
 * font and stacking contexts don't leak in.
 */
export function PreviewDialog({
  title,
  controls,
  onClose,
  children,
}: {
  title: string;
  controls?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="flex flex-col w-full max-w-5xl h-[85vh] rounded-xl overflow-hidden bg-[hsl(var(--aui-background))] border border-[hsl(var(--claude-border))] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-2 border-b border-[hsl(var(--claude-border))] font-sans">
          <span className="text-sm font-medium text-[hsl(var(--aui-foreground))]">
            {title}
          </span>
          <div className="flex items-center gap-2">
            {controls}
            <button
              onClick={onClose}
              className="p-1.5 rounded hover:bg-[hsl(var(--claude-hover))] transition-colors"
              title="Close (Esc)"
            >
              <XIcon className="w-4 h-4" />
            </button>
          </div>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
