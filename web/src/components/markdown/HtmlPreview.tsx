import { useEffect, useState, type FC } from "react";
import { createPortal } from "react-dom";
import { PlayIcon, XIcon } from "lucide-react";
import type { CodeHeaderProps } from "@assistant-ui/react-markdown";
import { CodeHeaderBar, HeaderButton } from "./CodeHeaderBar";

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
      {isOpen &&
        createPortal(
          <HtmlPreviewDialog code={code} onClose={() => setIsOpen(false)} />,
          document.body,
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
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="flex flex-col w-full max-w-5xl h-[85vh] rounded-xl overflow-hidden bg-[hsl(var(--aui-background))] border border-[hsl(var(--claude-border))] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-[hsl(var(--claude-border))]">
          <span className="text-sm font-medium text-[hsl(var(--aui-foreground))]">
            HTML preview
          </span>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-[hsl(var(--claude-hover))] transition-colors"
            title="Close (Esc)"
          >
            <XIcon className="w-4 h-4" />
          </button>
        </div>
        <iframe
          sandbox="allow-scripts"
          srcDoc={code}
          title="HTML preview"
          className="flex-1 w-full bg-white"
        />
      </div>
    </div>
  );
}
