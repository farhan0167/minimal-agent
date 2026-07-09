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
  return (
    <div className="text-sm rounded-lg overflow-hidden max-h-80 overflow-y-auto bg-[hsl(var(--claude-code-bg))] border border-[hsl(var(--claude-border))]">
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
