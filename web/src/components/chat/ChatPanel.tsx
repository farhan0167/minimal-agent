import { useEffect, useRef, useState } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useChatRuntime } from "../../hooks/use-chat-runtime";
import type { ReasoningState } from "../../hooks/use-chat-runtime";
import { getTools } from "../../api/tools";
import { buildToolUIs } from "../tools";
import { Thread } from "./Thread";

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
      <div className="flex items-center justify-center h-full text-sm text-app-fg-muted">
        Loading conversation...
      </div>
    );
  }

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {toolUIs.map((ToolUI, i) => (
        <ToolUI key={i} />
      ))}

      <div className="h-full min-h-0">
        <Thread reasoning={reasoning} onReasoningChange={setReasoning} />
      </div>
    </AssistantRuntimeProvider>
  );
}
