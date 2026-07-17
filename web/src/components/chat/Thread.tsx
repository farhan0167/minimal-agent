import { AuiIf, ThreadPrimitive } from "@assistant-ui/react";
import { ArrowDownIcon } from "lucide-react";
import type { ReasoningState } from "../../hooks/use-chat-runtime";
import { Button } from "../ui/Button";
import { Text } from "../ui/Text";
import { AssistantMessage } from "./AssistantMessage";
import { UserMessage } from "./UserMessage";
import { Composer } from "./Composer";

interface ThreadProps {
  /** Per-turn reasoning knobs, owned by ChatPanel, rendered in the composer. */
  reasoning: ReasoningState;
  onReasoningChange: (next: ReasoningState) => void;
}

/**
 * The chat shell: scrollable viewport, message list, and the sticky composer
 * footer, built directly on ThreadPrimitive. Auto-scroll, scroll-to-bottom
 * state, and footer height tracking all come from the primitives; this file
 * owns only the column layout (one centered 50rem column, the same width for
 * messages and composer).
 */
export function Thread({ reasoning, onReasoningChange }: ThreadProps) {
  return (
    <ThreadPrimitive.Root className="chat-thread flex h-full flex-col bg-app-bg">
      <ThreadPrimitive.Viewport className="flex flex-1 flex-col overflow-y-auto">
        <div className="mx-auto flex w-full max-w-[50rem] flex-1 flex-col px-4 pt-8">
          <AuiIf condition={(s) => s.thread.isEmpty}>
            <div className="flex flex-1 items-center justify-center">
              <Text variant="prose" muted className="text-xl">
                How can I help you today?
              </Text>
            </div>
          </AuiIf>
          <ThreadPrimitive.Messages>
            {({ message }) =>
              message.role === "user" ? <UserMessage /> : <AssistantMessage />
            }
          </ThreadPrimitive.Messages>
        </div>
        <ThreadPrimitive.ViewportFooter className="sticky bottom-0 mx-auto w-full max-w-[50rem] bg-app-bg px-4 pb-5 pt-2">
          <div className="relative">
            <ThreadPrimitive.ScrollToBottom asChild>
              <Button
                variant="icon"
                aria-label="Scroll to bottom"
                className="absolute -top-10 left-1/2 -translate-x-1/2 rounded-full border border-app-border bg-app-surface p-2 disabled:hidden"
              >
                <ArrowDownIcon className="w-4 h-4" />
              </Button>
            </ThreadPrimitive.ScrollToBottom>
            <Composer
              reasoning={reasoning}
              onReasoningChange={onReasoningChange}
            />
          </div>
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
}
