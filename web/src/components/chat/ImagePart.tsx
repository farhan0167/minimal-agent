import { useMessagePartImage } from "@assistant-ui/react";

/**
 * Inline `image` content part, wired into MessagePrimitive.Parts' Image slot
 * for both message roles. Covers a reloaded user message's attachments (which
 * come back from the server as image parts, not attachments) and the agent
 * loop's harness flush (images from an image/PDF read rendered mid-turn) —
 * sized to match AttachmentImage so the live and reloaded renderings of the
 * same image agree.
 */
export function ImagePart() {
  const { image } = useMessagePartImage();
  return (
    <img
      src={image}
      alt=""
      className="block max-w-full h-auto rounded-ctl my-2"
      style={{ maxHeight: "20rem" }}
    />
  );
}
