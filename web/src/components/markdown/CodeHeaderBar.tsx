import { useState, type ReactNode } from "react";
import { CheckIcon, CopyIcon } from "lucide-react";
import { Button } from "../ui/Button";

/**
 * Replacement code-block header for fences with extra controls: language
 * label on the left, custom action buttons + copy on the right. Mirrors
 * assistant-ui's DefaultCodeHeader (and reuses its .aui-code-header-* CSS)
 * so custom-headed blocks look identical to plain ones.
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
    <div className="aui-code-header-root flex items-center justify-between gap-2 px-4 py-1.5 text-sm font-sans rounded-t-lg">
      <span className="aui-code-header-language lowercase">{language}</span>
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
    <Button variant="ghost" size="sm" onClick={onClick} title={title} className="px-2 py-1 font-sans">
      {children}
    </Button>
  );
}
