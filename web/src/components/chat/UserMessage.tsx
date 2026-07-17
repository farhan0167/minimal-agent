import {
  AuiIf,
  ActionBarPrimitive,
  MessagePartPrimitive,
  MessagePrimitive,
} from "@assistant-ui/react";
import { PencilIcon } from "lucide-react";
import { Button } from "../ui/Button";
import { AttachmentImage } from "./AttachmentImage";
import { AttachmentChip } from "./AttachmentChip";
import { BranchPicker } from "./BranchPicker";
import { EditComposer } from "./EditComposer";
import { ImagePart } from "./ImagePart";

/**
 * Inline image attachment for the user's own message. A reloaded turn comes
 * back from the server as inline `image` content parts (ImagePart), so the
 * live turn renders its attachments the same way — a real image in the
 * bubble, not a chip. Non-image attachments (PDFs) fall through to the chip.
 */
function MessageAttachment() {
  return (
    <AttachmentImage
      Fallback={AttachmentChip}
      className="block w-full h-auto"
      maxHeight="20rem"
    />
  );
}

/** User text is an utterance, not markdown — preserve the typed line breaks. */
function UserText() {
  return (
    <p className="whitespace-pre-wrap break-words">
      <MessagePartPrimitive.Text />
    </p>
  );
}

/**
 * User message: a right-aligned bubble holding attachments (stacked above the
 * text, inside the bubble, so live and reloaded turns look identical), with
 * an edit pencil on hover and a branch picker once an edit created branches.
 * While the message's composer is editing, the bubble is replaced in place by
 * the EditComposer.
 */
export function UserMessage() {
  return (
    <MessagePrimitive.Root className="flex w-full flex-col items-end py-2">
      <AuiIf condition={(s) => s.message.composer.isEditing}>
        <div className="w-full max-w-[80%]">
          <EditComposer />
        </div>
      </AuiIf>
      <AuiIf condition={(s) => !s.message.composer.isEditing}>
        <div className="flex max-w-[80%] items-center gap-1">
          {/* Fixed-width slot: the edit pencil mounts/unmounts with hover
              (autohide), and inside this width-capped row a long bubble would
              otherwise shrink and rewrap the moment it appears. */}
          <div className="flex w-7 shrink-0 justify-center">
            <ActionBarPrimitive.Root
              hideWhenRunning
              autohide="always"
              className="flex items-center"
            >
              <ActionBarPrimitive.Edit asChild>
                <Button variant="icon" size="sm" aria-label="Edit message">
                  <PencilIcon className="w-3.5 h-3.5" />
                </Button>
              </ActionBarPrimitive.Edit>
            </ActionBarPrimitive.Root>
          </div>
          <div className="chat-user-bubble min-w-0">
            <AuiIf
              condition={(s) =>
                s.message.role === "user" && s.message.attachments.length > 0
              }
            >
              <div className="chat-user-attachments">
                <MessagePrimitive.Attachments>
                  {() => <MessageAttachment />}
                </MessagePrimitive.Attachments>
              </div>
            </AuiIf>
            <MessagePrimitive.Parts
              components={{ Text: UserText, Image: ImagePart }}
            />
          </div>
        </div>
        <BranchPicker className="mt-1" />
      </AuiIf>
    </MessagePrimitive.Root>
  );
}
