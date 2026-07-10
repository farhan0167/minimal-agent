import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Standalone markdown for tool results. The assistant's MarkdownText is bound
 * to assistant-ui's message-part context and can't render arbitrary strings,
 * so tool cards use react-markdown directly with the same .aui-md styles.
 */
export function ToolMarkdown({ text }: { text: string }) {
  return (
    <div className="aui-md text-sm max-h-80 overflow-y-auto p-3 rounded-lg bg-[hsl(var(--claude-hover))]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: (props) => (
            <a
              {...props}
              target="_blank"
              rel="noreferrer"
              className="underline text-[hsl(var(--aui-primary))]"
            />
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
