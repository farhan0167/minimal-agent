import type { Session } from "../../types/session";
import { formatTokens } from "../../lib/format";
import { Bot } from "lucide-react";

interface HeaderProps {
  session: Session | null;
}

export function Header({ session }: HeaderProps) {
  if (!session) {
    return (
      <header className="flex items-center h-14 px-6 border-b border-[hsl(var(--claude-border))] bg-[hsl(var(--aui-background))]">
        <h1 className="text-sm font-medium text-[hsl(var(--aui-muted-foreground))] font-serif">
          minimal-agent
        </h1>
      </header>
    );
  }

  return (
    <header className="flex items-center justify-between h-14 px-6 border-b border-[hsl(var(--claude-border))] bg-[hsl(var(--aui-background))]">
      <div className="flex items-center gap-3">
        <Bot className="w-4 h-4 text-[hsl(var(--aui-primary))]" />
        <span className="text-sm font-medium text-[hsl(var(--aui-foreground))] font-serif">
          {session.model}
        </span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-[hsl(var(--aui-primary)/0.08)] text-[hsl(var(--aui-primary))] border border-[hsl(var(--aui-primary)/0.19)]">
          {session.backend}
        </span>
      </div>

      {session.usage && (
        <div className="text-xs text-[hsl(var(--aui-muted-foreground))]">
          {formatTokens(session.usage.total_tokens)} tokens
        </div>
      )}
    </header>
  );
}
