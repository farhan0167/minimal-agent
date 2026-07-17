import { ShikiSyntaxHighlighter } from "../chat/ShikiHighlighter";

/**
 * Syntax-highlighted code inside a tool-call card, reusing the app's Shiki
 * instance (dual light/dark themes, lazy language loading).
 */
export function CodeBlock({
  code,
  language,
}: {
  code: string;
  language: string;
}) {
  // No max-height here: the .shiki-wrapper inside owns vertical scrolling
  // (index.css). A second cap on this wrapper would nest two scroll
  // containers and show double scrollbars.
  return (
    <div className="text-sm rounded-ctl overflow-hidden bg-app-code-bg border border-app-border">
      <ShikiSyntaxHighlighter
        language={language}
        code={code}
        components={{
          Pre: (props) => <pre className="p-3 overflow-x-auto" {...props} />,
          Code: (props) => <code className="font-mono text-[0.8rem]" {...props} />,
        }}
      />
    </div>
  );
}
