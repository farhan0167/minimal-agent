import {
  AttachmentUI,
  Composer as DefaultComposer,
} from "@assistant-ui/react-ui";
import { AttachmentImage } from "./AttachmentImage";

/**
 * Pending-attachment preview in the composer.
 *
 * The prebuilt composer shows an uploaded-but-unsent image as a generic file
 * chip ("image.png / Image") with no visible preview — the pending attachment
 * only holds the raw `File`, and the default chip's thumbnail doesn't surface
 * it. This renders a real thumbnail instead; non-image attachments (PDFs) fall
 * through to the default chip.
 */
function ComposerAttachment() {
  return (
    <AttachmentImage
      Fallback={AttachmentUI}
      className="aui-composer-image-attachment"
      maxHeight="8rem"
    />
  );
}

/**
 * Composer that previews pending image attachments as thumbnails.
 *
 * Reproduces the prebuilt composer layout (attachments strip → add button →
 * input → action) but swaps the chip-based Attachment slot for
 * {@link ComposerAttachment}. Everything else — input, send/cancel, the attach
 * button — is the default.
 */
export function Composer() {
  return (
    <DefaultComposer.Root>
      {/* align-items:end so mixed-height items (image thumbnails vs. file
          chips) sit on a common baseline; flex-wrap so multiple uploads
          don't overflow the row. */}
      <div
        className="aui-composer-attachments"
        style={{ alignItems: "flex-end", flexWrap: "wrap" }}
      >
        <DefaultComposer.Attachments
          components={{ Attachment: ComposerAttachment }}
        />
      </div>
      <DefaultComposer.AddAttachment />
      <DefaultComposer.Input autoFocus />
      <DefaultComposer.Action />
    </DefaultComposer.Root>
  );
}
