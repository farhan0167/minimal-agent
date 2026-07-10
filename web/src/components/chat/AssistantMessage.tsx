import { MessagePrimitive } from "@assistant-ui/react";
import {
  AssistantActionBar,
  BranchPicker,
  AssistantMessage as DefaultAssistantMessage,
} from "@assistant-ui/react-ui";
import { makeReasoningPart } from "./ReasoningPart";

/**
 * Custom assistant message body.
 *
 * The prebuilt <Thread> renders assistant messages through a fixed component
 * set that has no reasoning slot, so a reasoning content part would be
 * silently dropped. We reproduce the default layout (avatar → content →
 * branch picker → action bar) but render the content ourselves via
 * MessagePrimitive.Content, which DOES expose a `Reasoning` slot.
 *
 * Text renders with the app's markdown component; tool calls resolve from the
 * globally-registered `makeAssistantToolUI` components (via the runtime's
 * model context), exactly as they did under the default message.
 */
export function makeAssistantMessage(Text: React.ComponentType) {
  // Reasoning renders through the same markdown component as answer text.
  const Reasoning = makeReasoningPart(Text);
  return function AssistantMessage() {
    return (
      <DefaultAssistantMessage.Root>
        <DefaultAssistantMessage.Avatar />
        <div className="aui-assistant-message-content">
          <MessagePrimitive.Content
            components={{
              Text: Text as never,
              Reasoning,
            }}
          />
        </div>
        <BranchPicker />
        <AssistantActionBar />
      </DefaultAssistantMessage.Root>
    );
  };
}
