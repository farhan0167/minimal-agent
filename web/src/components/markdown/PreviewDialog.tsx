import { useRef, type ReactNode } from "react";
import { MinusIcon, PlusIcon } from "lucide-react";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { useWheelZoom, type Zoom } from "./use-zoom";

export function ZoomControls({ zoom, zoomBy, reset }: Zoom) {
  return (
    <div className="flex items-center font-ui text-app-fg">
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
 * Shared modal chrome for rich-content previews (HTML, SVG, Mermaid).
 *
 * The overlay, Esc/backdrop close, focus trap and scroll lock now come from
 * <Dialog>; this is only the size choice and the zoom controls slot. Always
 * mounted open — callers conditionally render it rather than passing `open`.
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
  return (
    <Dialog open onClose={onClose} title={title} size="full" controls={controls}>
      {children}
    </Dialog>
  );
}
