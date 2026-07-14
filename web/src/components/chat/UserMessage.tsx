import { MessagePrimitive } from "@assistant-ui/react";
import {
  AttachmentUI,
  BranchPicker,
  UserActionBar,
  UserMessage as DefaultUserMessage,
} from "@assistant-ui/react-ui";
import { AttachmentImage } from "./AttachmentImage";

/**
 * Inline image attachment for the user's own message.
 *
 * The prebuilt <Thread> renders a sent image as an attachment *chip*
 * (thumbnail + "image.png / Image"), while the reload path renders the same
 * image as an inline `image` content part (the core's default Image slot). So
 * the live turn and the reloaded turn look different — a chip live, the full
 * image after refresh. Rendering the image inline closes that gap; non-image
 * attachments (PDFs) fall through to the default chip.
 */
function MessageAttachment() {
  return (
    <AttachmentImage
      Fallback={AttachmentUI}
      className="aui-user-message-image-attachment"
      maxHeight="20rem"
    />
  );
}

/**
 * User message body that renders image attachments *inside* the message bubble,
 * above the text.
 *
 * The prebuilt layout puts attachments in their own grid row (grid-row 1, no
 * bubble) and the text in a separate bubbled row (grid-row 2) — so a live turn
 * shows the image floating above a detached text bubble. On reload the image
 * comes back as an inline `image` content part *inside* that bubble, so the two
 * look different (separated live, contained after refresh).
 *
 * We close that gap by rendering the attachments and the text in one shared
 * `aui-user-message-content` bubble. When the message has attachments we build
 * the bubble ourselves (images stacked over text); when it has none we defer to
 * the default Content so a plain text turn is untouched.
 */
export function UserMessage() {
  return (
    <DefaultUserMessage.Root>
      <MessagePrimitive.If hasAttachments>
        <div className="aui-user-message-content">
          <div className="aui-user-message-attachments-inline">
            <MessagePrimitive.Attachments
              components={{ Attachment: MessageAttachment }}
            />
          </div>
          <MessagePrimitive.If hasContent>
            <MessagePrimitive.Content />
          </MessagePrimitive.If>
        </div>
        <UserActionBar />
      </MessagePrimitive.If>
      <MessagePrimitive.If hasAttachments={false}>
        <MessagePrimitive.If hasContent>
          <UserActionBar />
          <DefaultUserMessage.Content />
        </MessagePrimitive.If>
      </MessagePrimitive.If>
      <BranchPicker />
    </DefaultUserMessage.Root>
  );
}
