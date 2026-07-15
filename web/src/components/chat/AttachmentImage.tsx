import { useEffect, useMemo } from "react";
import { AttachmentPrimitive, useAttachment } from "@assistant-ui/react";
import { CircleXIcon } from "lucide-react";

/**
 * The image data URI for the current attachment, or undefined if it isn't an
 * image (or the data isn't available yet).
 *
 * Two sources, by lifecycle:
 * - **Sent / reloaded** attachments carry the image in `content` as a data URI
 *   (SimpleImageAttachmentAdapter.send() puts it there).
 * - **Pending** composer attachments only have the raw `File`; we mint an
 *   object URL for it in an effect and revoke it on cleanup. Minting in the
 *   selector instead would leak a URL every render and loop forever (#185).
 *
 * Each `useAttachment` selector returns a stable primitive (string|undefined),
 * never a fresh object — object results are reference-compared and re-render
 * forever.
 */
function useAttachmentImageSrc(): string | undefined {
  const contentSrc = useAttachment((a) =>
    a.type === "image"
      ? a.content?.find((c) => c.type === "image")?.image
      : undefined,
  );
  const file = useAttachment((a) => (a.type === "image" ? a.file : undefined));

  // Compute the object URL during render (available on first paint, no flash),
  // and revoke it on unmount / when the file changes. `content` wins when
  // present, so we only mint a URL for a still-pending composer attachment.
  const fileSrc = useMemo(
    () => (!contentSrc && file ? URL.createObjectURL(file) : undefined),
    [file, contentSrc],
  );
  useEffect(() => {
    if (!fileSrc) return;
    return () => URL.revokeObjectURL(fileSrc);
  }, [fileSrc]);

  return contentSrc ?? fileSrc;
}

/**
 * Renders an image attachment inline as an `<img>`. Non-image attachments (and
 * images whose data isn't ready) fall back to `Fallback` — the caller passes
 * the default chip component so PDFs and the like still render normally.
 */
export function AttachmentImage({
  Fallback,
  className,
  maxHeight,
}: {
  Fallback: React.ComponentType;
  className?: string;
  maxHeight: string;
}) {
  const src = useAttachmentImageSrc();
  const name = useAttachment((a) => a.name);
  // Pending / composer attachments are removable; a sent message's attachment
  // (source === "message") is not — matches the default AttachmentUI.
  const canRemove = useAttachment((a) => a.source !== "message");

  if (!src) return <Fallback />;

  return (
    <AttachmentPrimitive.Root
      className="aui-attachment-root"
      style={{ display: "inline-block" }}
    >
      <img
        src={src}
        alt={name}
        className={className}
        style={{
          display: "block",
          maxWidth: "100%",
          maxHeight,
          borderRadius: "0.5rem",
        }}
      />
      {canRemove && (
        <AttachmentPrimitive.Remove
          className="aui-attachment-remove"
          aria-label="Remove file"
        >
          <CircleXIcon />
        </AttachmentPrimitive.Remove>
      )}
    </AttachmentPrimitive.Root>
  );
}
