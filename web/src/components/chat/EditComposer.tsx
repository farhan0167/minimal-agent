import { ComposerPrimitive } from "@assistant-ui/react";
import { Button } from "../ui/Button";

/**
 * In-place editor for a sent user message. Rendered by UserMessage when the
 * message's composer enters editing (the ActionBar edit pencil); because it
 * mounts inside the message scope, ComposerPrimitive.Root binds to that
 * message's edit composer automatically — Send commits the edit as a new
 * branch, Cancel exits without one.
 */
export function EditComposer() {
  return (
    <ComposerPrimitive.Root className="chat-user-bubble flex w-full flex-col">
      <ComposerPrimitive.Input
        autoFocus
        className="w-full resize-none bg-transparent outline-none text-base px-1 py-1"
      />
      <div className="flex justify-end gap-2 pt-2">
        <ComposerPrimitive.Cancel asChild>
          <Button variant="ghost" size="sm">
            Cancel
          </Button>
        </ComposerPrimitive.Cancel>
        {/* No type="submit" — see Composer.tsx: onClick sends; a form submit
            on top of it would send again into the already-ended composer. */}
        <ComposerPrimitive.Send asChild>
          <Button variant="primary" size="sm">
            Update
          </Button>
        </ComposerPrimitive.Send>
      </div>
    </ComposerPrimitive.Root>
  );
}
