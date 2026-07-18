import { AuiIf, ComposerPrimitive } from "@assistant-ui/react";
import { ArrowUpIcon, PaperclipIcon, SquareIcon } from "lucide-react";
import type { ReasoningState } from "../../hooks/use-chat-runtime";
import { Button } from "../ui/Button";
import { AttachmentImage } from "./AttachmentImage";
import { AttachmentChip } from "./AttachmentChip";
import { ReasoningControls } from "./ReasoningControls";

/**
 * Pending-attachment preview in the composer: images as real thumbnails,
 * everything else (PDFs) as the generic chip.
 */
function ComposerAttachment() {
  return (
    <AttachmentImage
      Fallback={AttachmentChip}
      className="rounded-ctl"
      maxHeight="8rem"
    />
  );
}

interface ComposerProps {
  reasoning: ReasoningState;
  onReasoningChange: (next: ReasoningState) => void;
}

/**
 * The thread composer — the floating input at the bottom of the chat.
 *
 * Built on ComposerPrimitive (form submission, Enter-to-send, focus
 * management, paste-to-attach all come from the primitive); this file owns
 * only the layout: attachments strip → input → attach + reasoning controls /
 * send-or-stop. The frame's look is `.chat-composer` in index.css.
 */
export function Composer({ reasoning, onReasoningChange }: ComposerProps) {
  return (
    <ComposerPrimitive.Root className="chat-composer flex flex-col">
      {/* align-items:end so mixed-height items (image thumbnails vs. file
          chips) sit on a common baseline; flex-wrap so multiple uploads
          don't overflow the row. Collapses entirely when empty. */}
      <div className="flex flex-wrap items-end gap-2 px-4 pt-3 empty:hidden">
        <ComposerPrimitive.Attachments>
          {() => <ComposerAttachment />}
        </ComposerPrimitive.Attachments>
      </div>
      <ComposerPrimitive.Input
        autoFocus
        rows={1}
        placeholder="Send a message..."
        className="w-full resize-none bg-transparent outline-none text-base px-6 pt-5 pb-2 placeholder:text-app-fg-muted"
      />
      <div className="flex items-center px-2.5 pb-2.5 pt-1">
        <ComposerPrimitive.AddAttachment asChild>
          <Button variant="icon" aria-label="Attach a file">
            <PaperclipIcon className="w-4 h-4" />
          </Button>
        </ComposerPrimitive.AddAttachment>
        <div className="ml-2">
          <ReasoningControls value={reasoning} onChange={onReasoningChange} />
        </div>
        <div className="flex-1" />
        {/* Send while idle; stop while a run is in flight. (Not
            s.composer.canCancel — that reflects the runtime's cancel
            *capability*, which LocalRuntime always has.) */}
        <AuiIf condition={(s) => !s.thread.isRunning}>
          {/* No type="submit": the action button sends via onClick, and the
              form's own submit handler would send a second time (into an
              already-ended composer, in the edit case). */}
          <ComposerPrimitive.Send asChild>
            <Button variant="primary" size="icon" aria-label="Send message">
              <ArrowUpIcon className="w-4 h-4" />
            </Button>
          </ComposerPrimitive.Send>
        </AuiIf>
        <AuiIf condition={(s) => s.thread.isRunning}>
          <ComposerPrimitive.Cancel asChild>
            <Button variant="primary" size="icon" aria-label="Stop generating">
              <SquareIcon className="w-3.5 h-3.5 fill-current" />
            </Button>
          </ComposerPrimitive.Cancel>
        </AuiIf>
      </div>
    </ComposerPrimitive.Root>
  );
}
