import { AttachmentPrimitive, useAttachment } from "@assistant-ui/react";
import { CircleXIcon, FileTextIcon } from "lucide-react";
import { Button } from "../ui/Button";
import { Text } from "../ui/Text";

/**
 * Generic attachment chip — icon, filename, kind — for attachments with no
 * richer rendering (PDFs and other documents; images render inline through
 * AttachmentImage, which uses this as its fallback). Owned replacement for
 * the chip that left with @assistant-ui/react-ui.
 */
export function AttachmentChip() {
  const kind = useAttachment((a) => a.type);
  // Pending / composer attachments are removable; a sent message's are not.
  const canRemove = useAttachment((a) => a.source !== "message");

  return (
    <AttachmentPrimitive.Root className="flex items-center gap-2 bg-app-surface border border-app-border rounded-ctl px-3 py-2">
      <FileTextIcon aria-hidden className="w-4 h-4 shrink-0 text-app-fg-muted" />
      <div className="flex flex-col min-w-0">
        {/* Name renders bare text and takes no props — the span owns the look. */}
        <span className="text-sm truncate text-app-fg">
          <AttachmentPrimitive.Name />
        </span>
        <Text variant="caption" className="capitalize">
          {kind}
        </Text>
      </div>
      {canRemove && (
        <AttachmentPrimitive.Remove asChild>
          <Button variant="icon" size="sm" aria-label="Remove file">
            <CircleXIcon className="w-3.5 h-3.5" />
          </Button>
        </AttachmentPrimitive.Remove>
      )}
    </AttachmentPrimitive.Root>
  );
}
