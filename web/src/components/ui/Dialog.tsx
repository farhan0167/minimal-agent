import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { XIcon } from "lucide-react";
import { Button } from "./Button";
import { Text } from "./Text";

/**
 * The modal.
 *
 * Owns the overlay, Escape-to-close, backdrop-click-to-close, the focus trap,
 * scroll lock, and focus restore — every one of which was reimplemented (or
 * quietly skipped) per dialog. PreviewDialog handled Escape but not focus;
 * NewSessionDialog leaned on <dialog>'s native modal and got focus for free but
 * used a bg-black/40 literal for the backdrop.
 *
 * This is a portal + a div rather than <dialog> because the two call sites
 * disagree on what the panel is: one is a form, one is a full-height viewer.
 * <dialog>'s ::backdrop cannot read --app-overlay without a second selector,
 * and its top-layer stacking fights the zoom pane. The behaviour it gives away
 * for free is written out below, once.
 */

export type DialogSize = "md" | "full";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  size?: DialogSize;
  /** Rendered in the header, before the close button (zoom controls, etc.). */
  controls?: ReactNode;
  children: ReactNode;
}

const SIZES: Record<DialogSize, string> = {
  md: "w-full max-w-md",
  full: "w-full max-w-5xl h-[85vh]",
};

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Dialog({
  open,
  onClose,
  title,
  size = "md",
  controls,
  children,
}: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    // Restoring focus to whatever opened the dialog is the half of the contract
    // that is invisible when it works and jarring when it doesn't: without it
    // focus falls back to <body> on close and keyboard users start over.
    const opener = document.activeElement as HTMLElement | null;
    panelRef.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab") return;

      // Trap: wrap Tab at the panel's edges so focus can't escape to the page
      // behind the overlay, which is still there and still clickable.
      const items = panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (!items?.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = prevOverflow;
      opener?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-app-overlay p-4"
      onClick={onClose}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        className={`flex flex-col overflow-hidden bg-app-bg border border-app-border
          rounded-surface shadow-(--app-shadow) ${SIZES[size]}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-2 px-4 py-2 border-b border-app-border">
          <Text variant="label" as="h2">
            {title}
          </Text>
          <div className="flex items-center gap-2">
            {controls}
            <Button
              variant="icon"
              onClick={onClose}
              title="Close (Esc)"
              aria-label="Close"
            >
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
