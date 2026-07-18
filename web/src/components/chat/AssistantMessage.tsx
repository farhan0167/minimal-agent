import {
  AuiIf,
  ActionBarPrimitive,
  MessagePrimitive,
} from "@assistant-ui/react";
import { CheckIcon, CopyIcon, RefreshCwIcon } from "lucide-react";
import { Button } from "../ui/Button";
import { MarkdownText } from "./MarkdownText";
import { ReasoningPart } from "./ReasoningPart";
import { ImagePart } from "./ImagePart";
import { BranchPicker } from "./BranchPicker";

/**
 * Assistant message: the full agent turn — reasoning traces, tool calls, and
 * answer text as ordered parts. Text and reasoning render through the app's
 * markdown component; tool calls resolve from the globally-registered
 * `makeAssistantToolUI` components (via the runtime's model context); images
 * (the harness flush mid-turn) render inline.
 *
 * The action bar (copy / regenerate) shows on the last message and on hover
 * for earlier ones; the branch picker appears once regeneration created
 * branches.
 */
export function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="w-full py-2">
      <div className="chat-message-body">
        <MessagePrimitive.Parts
          components={{
            Text: MarkdownText,
            Reasoning: ReasoningPart,
            Image: ImagePart,
          }}
        />
      </div>
      {/* Fixed-height row: the action bar mounts/unmounts with hover
          (autohide), so without a reserved height its appearance would push
          every message below it down. */}
      <div className="mt-1 flex h-7 items-center gap-2">
        <BranchPicker />
        <ActionBarPrimitive.Root
          hideWhenRunning
          autohide="not-last"
          className="flex items-center gap-1"
        >
          <ActionBarPrimitive.Copy asChild>
            <Button variant="icon" size="sm" aria-label="Copy message">
              <AuiIf condition={(s) => s.message.isCopied}>
                <CheckIcon className="w-3.5 h-3.5" />
              </AuiIf>
              <AuiIf condition={(s) => !s.message.isCopied}>
                <CopyIcon className="w-3.5 h-3.5" />
              </AuiIf>
            </Button>
          </ActionBarPrimitive.Copy>
          <ActionBarPrimitive.Reload asChild>
            <Button variant="icon" size="sm" aria-label="Regenerate reply">
              <RefreshCwIcon className="w-3.5 h-3.5" />
            </Button>
          </ActionBarPrimitive.Reload>
        </ActionBarPrimitive.Root>
      </div>
    </MessagePrimitive.Root>
  );
}
