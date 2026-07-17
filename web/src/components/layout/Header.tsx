import type { Session } from "../../types/session";
import { formatTokens } from "../../lib/format";
import { Bot, Moon, Sun } from "lucide-react";
import { useTheme } from "../../hooks/use-theme";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";

interface HeaderProps {
  session: Session | null;
}

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const label = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
  return (
    <Button
      variant="icon"
      onClick={toggleTheme}
      title={label}
      aria-label={label}
    >
      {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
    </Button>
  );
}

export function Header({ session }: HeaderProps) {
  if (!session) {
    return (
      <header className="flex items-center justify-between h-14 px-6 border-b border-[hsl(var(--claude-border))] bg-[hsl(var(--aui-background))]">
        <h1 className="text-sm font-medium text-[hsl(var(--aui-muted-foreground))] font-serif">
          minimal-agent
        </h1>
        <ThemeToggle />
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
        <Badge variant="accent" size="md">
          {session.backend}
        </Badge>
      </div>

      <div className="flex items-center gap-3">
        {session.usage && (
          <div className="text-xs text-[hsl(var(--aui-muted-foreground))]">
            {formatTokens(session.usage.total_tokens)} tokens
          </div>
        )}
        <ThemeToggle />
      </div>
    </header>
  );
}
