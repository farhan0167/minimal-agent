import type { Session } from "../../types/session";
import { SessionItem } from "./SessionItem";

interface SessionListProps {
  sessions: Session[];
  activeSessionId: string | null;
  isCollapsed: boolean;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => Promise<void>;
}

export function SessionList({
  sessions,
  activeSessionId,
  isCollapsed,
  onSelect,
  onDelete,
}: SessionListProps) {
  if (sessions.length === 0) {
    if (isCollapsed) return null;
    return (
      <p className="px-4 py-3 text-xs text-[hsl(var(--aui-muted-foreground))]">No sessions yet.</p>
    );
  }

  return (
    <div className="flex flex-col gap-1 px-2">
      {sessions.map((session) => (
        <SessionItem
          key={session.session_id}
          session={session}
          isActive={session.session_id === activeSessionId}
          isCollapsed={isCollapsed}
          onSelect={() => onSelect(session.session_id)}
          onDelete={() => onDelete(session.session_id)}
        />
      ))}
    </div>
  );
}
