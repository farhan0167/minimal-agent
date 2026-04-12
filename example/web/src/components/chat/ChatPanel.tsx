import { useEffect, useState } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { Thread, makeMarkdownText } from "@assistant-ui/react-ui";
import remarkGfm from "remark-gfm";
import { useChatRuntime } from "../../hooks/use-chat-runtime";
import { getTools } from "../../api/tools";
import { buildToolUIs } from "../tools";
import { ShikiSyntaxHighlighter } from "./ShikiHighlighter";

const MarkdownText = makeMarkdownText({
  remarkPlugins: [remarkGfm],
  components: {
    SyntaxHighlighter: ShikiSyntaxHighlighter,
  },
});

interface ChatPanelProps {
  sessionId: string;
  agentType: string;
}

export function ChatPanel({ sessionId, agentType }: ChatPanelProps) {
  const { runtime, isLoaded } = useChatRuntime(sessionId);
  const [toolUIs, setToolUIs] = useState<ReturnType<typeof buildToolUIs>>([]);

  useEffect(() => {
    getTools(agentType).then((tools) => {
      setToolUIs(buildToolUIs(tools.map((t) => t.name)));
    });
  }, [agentType]);

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

      <Thread assistantMessage={{ components: { Text: MarkdownText } }} />
    </AssistantRuntimeProvider>
  );
}
