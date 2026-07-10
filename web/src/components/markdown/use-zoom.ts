import { useCallback, useEffect, useState, type RefObject } from "react";

const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4;

export function useZoom() {
  const [zoom, setZoom] = useState(1);
  const zoomBy = useCallback((factor: number) => {
    setZoom((z) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z * factor)));
  }, []);
  const reset = useCallback(() => setZoom(1), []);
  return { zoom, zoomBy, reset };
}

export type Zoom = ReturnType<typeof useZoom>;

/**
 * Zoom on ctrl/meta + wheel — the gesture browsers use for page zoom (a
 * trackpad pinch arrives as ctrl+wheel too). Must be a non-passive native
 * listener so preventDefault() can stop the browser zooming the whole page.
 */
export function useWheelZoom(
  ref: RefObject<HTMLElement | null>,
  zoomBy: Zoom["zoomBy"],
) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      zoomBy(e.deltaY < 0 ? 1.1 : 1 / 1.1);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [ref, zoomBy]);
}
