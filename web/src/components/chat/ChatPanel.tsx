import { useEffect, useState } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { Thread, makeMarkdownText } from "@assistant-ui/react-ui";
import remarkGfm from "remark-gfm";
import { useChatRuntime } from "../../hooks/use-chat-runtime";
import { getTools } from "../../api/tools";
import { buildToolUIs } from "../tools";
import { ShikiSyntaxHighlighter } from "./ShikiHighlighter";
import { makeAssistantMessage } from "./AssistantMessage";
import { HtmlCodeHeader } from "../markdown/HtmlPreview";
import { NullCodeHeader, SvgBlock } from "../markdown/SvgBlock";
import { MermaidBlock } from "../markdown/MermaidBlock";

const MarkdownText = makeMarkdownText({
  remarkPlugins: [remarkGfm],
  components: {
    SyntaxHighlighter: ShikiSyntaxHighlighter,
  },
  // Rich renderers for specific fence languages: html gets a sandboxed
  // preview button, svg/xml render live (sanitized), mermaid draws diagrams.
  componentsByLanguage: {
    html: { CodeHeader: HtmlCodeHeader },
    svg: { CodeHeader: NullCodeHeader, SyntaxHighlighter: SvgBlock },
    xml: { CodeHeader: NullCodeHeader, SyntaxHighlighter: SvgBlock },
    mermaid: { SyntaxHighlighter: MermaidBlock },
  },
});

// Custom assistant message so reasoning parts get rendered (the prebuilt
// Thread's default message has no reasoning slot). Text still uses markdown.
const AssistantMessage = makeAssistantMessage(MarkdownText);

interface ChatPanelProps {
  sessionId: string;
  agent: string | null;
}

export function ChatPanel({ sessionId, agent }: ChatPanelProps) {
  const { runtime, isLoaded } = useChatRuntime(sessionId);
  const [toolUIs, setToolUIs] = useState<ReturnType<typeof buildToolUIs>>([]);

  useEffect(() => {
    getTools(agent).then((tools) => {
      setToolUIs(buildToolUIs(tools.map((t) => t.name)));
    });
  }, [agent]);

  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-[hsl(var(--aui-muted-foreground))]">
        Loading conversation...
      </div>
    );
  }

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {toolUIs.map((ToolUI, i) => (
        <ToolUI key={i} />
      ))}

      <Thread components={{ AssistantMessage }} />
    </AssistantRuntimeProvider>
  );
}
