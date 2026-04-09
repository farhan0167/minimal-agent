import { useCallback, useRef, useState } from "react";
import type { Session, CreateSessionRequest } from "../../types/session";
import { SessionList } from "../session/SessionList";
import { NewSessionDialog } from "../session/NewSessionDialog";
import { Terminal, PanelLeftClose, PanelLeftOpen } from "lucide-react";

const MIN_WIDTH = 180;
const MAX_WIDTH = 480;
const DEFAULT_WIDTH = 256;
const COLLAPSED_WIDTH = 56;

interface SidebarProps {
  sessions: Session[];
  activeSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => Promise<void>;
  onCreate: (req: CreateSessionRequest) => Promise<Session>;
}

export function Sidebar({
  sessions,
  activeSessionId,
  onSelect,
  onDelete,
  onCreate,
}: SidebarProps) {
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsDragging(true);

      const startX = e.clientX;
      const startWidth = isCollapsed ? COLLAPSED_WIDTH : width;

      const handleMouseMove = (e: MouseEvent) => {
        const newWidth = startWidth + (e.clientX - startX);

        if (newWidth < MIN_WIDTH / 2) {
          setIsCollapsed(true);
        } else {
          setIsCollapsed(false);
          setWidth(Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, newWidth)));
        }
      };

      const handleMouseUp = () => {
        setIsDragging(false);
        document.removeEventListener("mousemove", handleMouseMove);
        document.removeEventListener("mouseup", handleMouseUp);
      };

      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    },
    [width, isCollapsed],
  );

  const currentWidth = isCollapsed ? COLLAPSED_WIDTH : width;

  return (
    <div className="relative flex" style={{ width: currentWidth }}>
      <aside
        ref={sidebarRef}
        className="flex flex-col h-full w-full border-r border-[hsl(var(--claude-border))] bg-[hsl(var(--claude-sidebar))]"
        style={{ width: currentWidth }}
      >
        {/* Brand + collapse toggle */}
        <div className="flex items-center justify-between h-14 px-3 border-b border-[hsl(var(--claude-border))]">
          {!isCollapsed && (
            <div className="flex items-center gap-2 min-w-0">
              <Terminal className="w-4 h-4 text-[hsl(var(--aui-primary))] shrink-0" />
              <span className="text-sm font-semibold text-[hsl(var(--aui-foreground))] truncate font-serif">
                minimal-agent
              </span>
            </div>
          )}
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className={`p-1.5 rounded-md hover:bg-[hsl(var(--claude-hover))] transition-colors shrink-0
              ${isCollapsed ? "mx-auto" : ""}`}
            title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isCollapsed ? (
              <PanelLeftOpen className="w-4 h-4 text-[hsl(var(--aui-muted-foreground))]" />
            ) : (
              <PanelLeftClose className="w-4 h-4 text-[hsl(var(--aui-muted-foreground))]" />
            )}
          </button>
        </div>

        {/* New session button */}
        <div className={isCollapsed ? "p-1.5" : "p-3"}>
          {isCollapsed ? (
            <button
              onClick={() => setIsCollapsed(false)}
              className="flex items-center justify-center w-full p-2 rounded-md
                hover:bg-[hsl(var(--claude-hover))] transition-colors"
              title="New Session"
            >
              <span className="text-lg text-[hsl(var(--aui-muted-foreground))]">+</span>
            </button>
          ) : (
            <NewSessionDialog onCreate={onCreate} />
          )}
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto">
          <SessionList
            sessions={sessions}
            activeSessionId={activeSessionId}
            isCollapsed={isCollapsed}
            onSelect={onSelect}
            onDelete={onDelete}
          />
        </div>
      </aside>

      {/* Drag handle */}
      <div
        onMouseDown={handleMouseDown}
        className={`absolute top-0 right-0 w-1 h-full cursor-col-resize z-10
          hover:bg-[hsl(var(--aui-primary)/0.25)] active:bg-[hsl(var(--aui-primary)/0.38)] transition-colors
          ${isDragging ? "bg-[hsl(var(--aui-primary)/0.38)]" : ""}`}
      />
    </div>
  );
}
