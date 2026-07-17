import type { Session } from "../../types/session";
import { formatTokens } from "../../lib/format";
import { Bot, Moon, Sun } from "lucide-react";
import { useTheme } from "../../hooks/use-theme";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { Text } from "../ui/Text";

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
      <header className="flex items-center justify-between h-14 px-6 border-b border-app-border bg-app-bg">
        <Text variant="prose" as="h1" muted className="text-sm font-medium">
          minimal-agent
        </Text>
        <ThemeToggle />
      </header>
    );
  }

  return (
    <header className="flex items-center justify-between h-14 px-6 border-b border-app-border bg-app-bg">
      <div className="flex items-center gap-3">
        <Bot className="w-4 h-4 text-app-accent" />
        <Text variant="prose" as="span" className="text-sm font-medium">
          {session.model}
        </Text>
        <Badge variant="accent" size="md">
          {session.backend}
        </Badge>
      </div>

      <div className="flex items-center gap-3">
        {session.usage && (
          <Text variant="caption">
            {formatTokens(session.usage.total_tokens)} tokens
          </Text>
        )}
        <ThemeToggle />
      </div>
    </header>
  );
}
