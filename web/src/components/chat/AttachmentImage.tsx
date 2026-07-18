import { useEffect, useState } from "react";
import { AttachmentPrimitive, useAttachment } from "@assistant-ui/react";
import { CircleXIcon } from "lucide-react";
import { Button } from "../ui/Button";

/**
 * The image data URI for the current attachment, or undefined if it isn't an
 * image (or the data isn't available yet).
 *
 * Two sources, by lifecycle:
 * - **Sent / reloaded** attachments carry the image in `content` as a data URI
 *   (SimpleImageAttachmentAdapter.send() puts it there).
 * - **Pending** composer attachments only have the raw `File`; we mint an
 *   object URL for it. Minting in the selector would leak a URL every render
 *   and loop forever (#185). Minting in a render-time useMemo breaks under
 *   StrictMode: the memo survives the simulated mount→cleanup→remount cycle,
 *   so cleanup revokes the very URL the remounted effect re-registers — a
 *   permanently broken thumbnail. So the URL is minted *inside* the effect
 *   and held in state: the StrictMode remount then mints a fresh one.
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

  // `content` wins when present, so a URL is only minted for a still-pending
  // composer attachment, and revoked when the file changes or on unmount.
  //
  // The set-state-in-effect rule is disabled deliberately: an object URL is an
  // external resource whose lifecycle must be tied to the effect (mint on
  // setup, revoke on cleanup) — the render-time alternatives either leak URLs
  // or hand out revoked ones under StrictMode (see above). The one extra
  // render per file change is the price of a correct lifecycle.
  /* eslint-disable react-hooks/set-state-in-effect */
  const [fileSrc, setFileSrc] = useState<string>();
  useEffect(() => {
    if (contentSrc || !file) {
      setFileSrc(undefined);
      return;
    }
    const url = URL.createObjectURL(file);
    setFileSrc(url);
    return () => {
      setFileSrc(undefined);
      URL.revokeObjectURL(url);
    };
  }, [file, contentSrc]);
  /* eslint-enable react-hooks/set-state-in-effect */

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
    <AttachmentPrimitive.Root className="relative inline-block">
      <img
        src={src}
        alt={name}
        className={`rounded-ctl ${className ?? ""}`}
        style={{
          display: "block",
          maxWidth: "100%",
          maxHeight,
        }}
      />
      {canRemove && (
        <AttachmentPrimitive.Remove asChild>
          <Button
            variant="icon"
            size="sm"
            aria-label="Remove file"
            className="absolute -top-2 -right-2 rounded-full bg-app-surface border border-app-border"
          >
            <CircleXIcon className="w-3.5 h-3.5" />
          </Button>
        </AttachmentPrimitive.Remove>
      )}
    </AttachmentPrimitive.Root>
  );
}
