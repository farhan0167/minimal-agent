import type { Session } from "../../types/session";
import { formatTimestamp } from "../../lib/format";
import { useSessionTitle } from "../../lib/session-titles";
import { Trash2, FolderOpen } from "lucide-react";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { Text } from "../ui/Text";

interface SessionItemProps {
  session: Session;
  isActive: boolean;
  isCollapsed: boolean;
  onSelect: () => void;
  onDelete: () => void;
}

export function SessionItem({
  session,
  isActive,
  isCollapsed,
  onSelect,
  onDelete,
}: SessionItemProps) {
  // Derived from the first user message; falls back to the raw id for
  // sessions that have no messages yet.
  const title = useSessionTitle(session.session_id) ?? session.session_id;

  if (isCollapsed) {
    return (
      <Button
        variant="ghost"
        block
        onClick={onSelect}
        title={title}
        aria-label={title}
        aria-current={isActive ? "true" : undefined}
        className={`p-2 ${isActive ? "bg-app-active" : ""}`}
      >
        <span
          aria-hidden
          className={`w-2 h-2 rounded-full ${
            isActive ? "bg-app-accent" : "bg-app-fg-muted"
          }`}
        />
      </Button>
    );
  }

  // The row is a container, not a control: the selectable area and the delete
  // action are siblings inside it. Previously delete was a <button> nested in
  // the row's <button> — invalid HTML, and it put an interactive <code> inside
  // a button too. Overlaying delete keeps the row's full width clickable
  // while leaving both controls independently reachable by keyboard.
  return (
    <div className="group relative">
      <Button
        variant="ghost"
        block
        onClick={onSelect}
        aria-current={isActive ? "true" : undefined}
        className={`justify-between px-3 py-2.5 pr-9 text-sm text-left ${
          isActive ? "bg-app-active text-app-fg" : ""
        }`}
      >
        {/* min-w-0 is what lets the truncations below actually truncate. */}
        <span className="block min-w-0 flex-1">
          <Text
            variant="prose"
            as="span"
            className="block truncate font-medium text-xs"
            title={session.session_id}
          >
            {title}
          </Text>

          <span
            className="flex items-center gap-1 text-[10px] text-app-fg-muted truncate mt-0.5
            bg-app-hover rounded px-1.5 py-0.5 font-mono"
          >
            <FolderOpen className="w-3 h-3 shrink-0" />
            <span className="truncate">
              {session.workspace_root ?? "no workspace"}
            </span>
          </span>

          {/* Agent, model & backend tags */}
          <span className="flex flex-wrap gap-1 mt-1.5">
            {session.agent && <Badge variant="accent">{session.agent}</Badge>}
            <Badge variant="neutral">{session.model}</Badge>
            <Badge variant="accent">{session.backend}</Badge>
          </span>

          <span className="block text-[10px] text-app-fg-muted mt-1">
            {formatTimestamp(session.updated_at)}
          </span>
        </span>
      </Button>

      <Button
        variant="danger"
        size="sm"
        onClick={onDelete}
        title="Delete session"
        aria-label={`Delete session ${title}`}
        className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
      >
        <Trash2 className="w-3 h-3" />
      </Button>
    </div>
  );
}
