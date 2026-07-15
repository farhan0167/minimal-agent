import { useEffect, useRef, useState } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { Thread, makeMarkdownText } from "@assistant-ui/react-ui";
import remarkGfm from "remark-gfm";
import { useChatRuntime } from "../../hooks/use-chat-runtime";
import type { ReasoningState } from "../../hooks/use-chat-runtime";
import { ReasoningControls } from "./ReasoningControls";
import { getTools } from "../../api/tools";
import { buildToolUIs } from "../tools";
import { ShikiSyntaxHighlighter } from "./ShikiHighlighter";
import { makeAssistantMessage } from "./AssistantMessage";
import { UserMessage } from "./UserMessage";
import { Composer } from "./Composer";
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
    mermaid: { CodeHeader: NullCodeHeader, SyntaxHighlighter: MermaidBlock },
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
  // Per-turn reasoning knobs. Held in state (to drive the controls) and
  // mirrored to a ref the runtime adapter reads at send time — the ref keeps
  // the memoized adapter stable across toggles (no runtime rebuild).
  // effort starts undefined ("Default"): nothing is sent for it until the
  // user picks a level, so the provider's default effort stays in charge.
  const [reasoning, setReasoning] = useState<ReasoningState>({ on: true });
  const reasoningRef = useRef(reasoning);
  useEffect(() => {
    reasoningRef.current = reasoning;
  }, [reasoning]);

  const { runtime, isLoaded } = useChatRuntime(sessionId, reasoningRef);
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

      {/* Flex column so the toolbar takes its natural height and the Thread
          (h-full internally) flexes to fill the rest — otherwise the Thread's
          bottom composer would overflow under the parent's overflow-hidden. */}
      <div className="flex flex-col h-full min-h-0">
        <ReasoningControls value={reasoning} onChange={setReasoning} />
        <div className="flex-1 min-h-0">
          <Thread components={{ AssistantMessage, UserMessage, Composer }} />
        </div>
      </div>
    </AssistantRuntimeProvider>
  );
}
