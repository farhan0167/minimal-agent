import type { Session } from "../../types/session";
import { formatTimestamp } from "../../lib/format";
import { Trash2, FolderOpen } from "lucide-react";

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
  if (isCollapsed) {
    return (
      <button
        onClick={onSelect}
        title={session.session_id}
        className={`
          flex items-center justify-center w-full p-2 rounded-md transition-colors
          ${isActive ? "bg-[hsl(var(--claude-active))]" : "hover:bg-[hsl(var(--claude-hover))]"}
        `}
      >
        <div className={`w-2 h-2 rounded-full ${isActive ? "bg-[hsl(var(--aui-primary))]" : "bg-[hsl(var(--aui-muted-foreground))]"}`} />
      </button>
    );
  }

  return (
    <button
      onClick={onSelect}
      className={`
        group flex items-center justify-between w-full px-3 py-2.5 text-left
        text-sm rounded-md transition-colors
        ${isActive ? "bg-[hsl(var(--claude-active))] text-[hsl(var(--aui-foreground))]" : "text-[hsl(var(--aui-muted-foreground))] hover:bg-[hsl(var(--claude-hover))]"}
      `}
    >
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium text-xs font-serif">
          {session.session_id}
        </div>
        <code
          onClick={(e) => {
            e.stopPropagation();
            const range = document.createRange();
            range.selectNodeContents(e.currentTarget.querySelector("span")!);
            const sel = window.getSelection();
            sel?.removeAllRanges();
            sel?.addRange(range);
          }}
          className="flex items-center gap-1 text-[10px] text-[hsl(var(--aui-muted-foreground))] truncate mt-0.5
          bg-[hsl(var(--claude-hover))] rounded px-1.5 py-0.5 font-mono cursor-text select-text">
          <FolderOpen className="w-3 h-3 shrink-0" />
          <span className="truncate">{session.workspace_root ?? "no workspace"}</span>
        </code>

        {/* Model & backend tags */}
        <div className="flex flex-wrap gap-1 mt-1.5">
          <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium
            rounded-full bg-[hsl(var(--claude-hover))] text-[hsl(var(--aui-muted-foreground))] border border-[hsl(var(--claude-border))]">
            {session.model}
          </span>
          <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium
            rounded-full bg-[hsl(var(--aui-primary)/0.06)] text-[hsl(var(--aui-primary))] border border-[hsl(var(--aui-primary)/0.15)]">
            {session.backend}
          </span>
        </div>

        <div className="text-[10px] text-[hsl(var(--aui-muted-foreground))] mt-1">
          {formatTimestamp(session.updated_at)}
        </div>
      </div>

      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="ml-2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-[hsl(var(--claude-active))] transition-opacity"
        title="Delete session"
      >
        <Trash2 className="w-3 h-3 text-[hsl(var(--aui-muted-foreground))]" />
      </button>
    </button>
  );
}
