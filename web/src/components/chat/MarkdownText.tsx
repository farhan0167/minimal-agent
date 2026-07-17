import {
  MarkdownTextPrimitive,
  type CodeHeaderProps,
} from "@assistant-ui/react-markdown";
import remarkGfm from "remark-gfm";
import { ShikiSyntaxHighlighter } from "./ShikiHighlighter";
import { CodeHeaderBar } from "../markdown/CodeHeaderBar";
import { HtmlCodeHeader } from "../markdown/HtmlPreview";
import { NullCodeHeader, SvgBlock } from "../markdown/SvgBlock";
import { MermaidBlock } from "../markdown/MermaidBlock";

/** Standard fence header: language label + copy button. */
const DefaultCodeHeader = ({ language, code }: CodeHeaderProps) => (
  <CodeHeaderBar language={language} code={code} />
);

/**
 * The app's markdown renderer, used for assistant answer text and reasoning
 * traces. Reads the current message part's text from assistant-ui's part
 * context (useMessagePartText — accepts reasoning parts too), so it takes no
 * props and can be dropped straight into a MessagePrimitive.Parts slot.
 *
 * Prose rhythm lives in index.css under `.chat-prose`; this file only decides
 * *what* renders: GFM, Shiki highlighting, and rich renderers for specific
 * fence languages — html gets a sandboxed preview button, svg/xml render live
 * (sanitized), mermaid draws diagrams.
 */
export function MarkdownText() {
  return (
    <MarkdownTextPrimitive
      className="chat-prose"
      remarkPlugins={[remarkGfm]}
      components={{
        SyntaxHighlighter: ShikiSyntaxHighlighter,
        CodeHeader: DefaultCodeHeader,
      }}
      componentsByLanguage={{
        html: { CodeHeader: HtmlCodeHeader },
        svg: { CodeHeader: NullCodeHeader, SyntaxHighlighter: SvgBlock },
        xml: { CodeHeader: NullCodeHeader, SyntaxHighlighter: SvgBlock },
        mermaid: {
          CodeHeader: NullCodeHeader,
          SyntaxHighlighter: MermaidBlock,
        },
      }}
    />
  );
}
