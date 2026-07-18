import { useState, type ReactNode } from "react";
import { CheckIcon, CopyIcon } from "lucide-react";
import { Button } from "../ui/Button";

/**
 * Code-block header: language label on the left, custom action buttons +
 * copy on the right. The app's default fence header (see MarkdownText), and
 * the shell that language-specific headers (html preview, svg toggle)
 * compose so every fence header looks identical. Colors come from
 * `.chat-code-header` in index.css (the code-bg/header/button tokens).
 */
export function CodeHeaderBar({
  language,
  code,
  children,
}: {
  language: string | undefined;
  code: string;
  children?: ReactNode;
}) {
  const [isCopied, setIsCopied] = useState(false);

  const onCopy = () => {
    if (!code || isCopied) return;
    navigator.clipboard.writeText(code).then(() => {
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    });
  };

  return (
    <div className="chat-code-header flex items-center justify-between gap-2 px-4 py-1.5 text-sm font-ui rounded-t-lg">
      <span className="lowercase">{language}</span>
      <div className="flex items-center gap-3">
        {children}
        <Button variant="icon" onClick={onCopy} title="Copy" aria-label="Copy code">
          {isCopied ? (
            <CheckIcon className="w-3.5 h-3.5" />
          ) : (
            <CopyIcon className="w-3.5 h-3.5" />
          )}
        </Button>
      </div>
    </div>
  );
}

/** Button styled to sit in a CodeHeaderBar's action area. */
export function HeaderButton({
  onClick,
  title,
  children,
}: {
  onClick: () => void;
  title: string;
  children: ReactNode;
}) {
  return (
    <Button variant="ghost" size="sm" onClick={onClick} title={title} className="px-2 py-1 font-ui">
      {children}
    </Button>
  );
}
