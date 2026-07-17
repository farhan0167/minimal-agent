import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { MinusIcon, PlusIcon, XIcon } from "lucide-react";
import { Button } from "../ui/Button";
import { useWheelZoom, type Zoom } from "./use-zoom";

export function ZoomControls({ zoom, zoomBy, reset }: Zoom) {
  return (
    <div className="flex items-center font-sans text-[hsl(var(--aui-foreground))]">
      <Button variant="icon" onClick={() => zoomBy(1 / 1.25)} title="Zoom out" aria-label="Zoom out">
        <MinusIcon className="w-4 h-4" />
      </Button>
      <Button
        variant="icon"
        onClick={reset}
        title="Reset zoom"
        aria-label="Reset zoom"
        className="w-12 py-1 text-xs tabular-nums"
      >
        {Math.round(zoom * 100)}%
      </Button>
      <Button variant="icon" onClick={() => zoomBy(1.25)} title="Zoom in" aria-label="Zoom in">
        <PlusIcon className="w-4 h-4" />
      </Button>
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-app-overlay p-4"
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
            <Button variant="icon" onClick={onClose} title="Close (Esc)" aria-label="Close preview">
              <XIcon className="w-4 h-4" />
            </Button>
          </div>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
