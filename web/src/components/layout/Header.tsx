import type { Session } from "../../types/session";
import { formatTokens } from "../../lib/format";
import { Bot, Moon, Sun } from "lucide-react";
import { useTheme } from "../../hooks/use-theme";
import { THEMES } from "../../themes";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { Select } from "../ui/Field";
import { Text } from "../ui/Text";

interface HeaderProps {
  session: Session | null;
}

// Mode toggle and theme picker share one useTheme() call. Two separate calls
// would each hold their own useState copy, so setTheme in one would not reach
// the other — a real fork the pre-paint <html> stamping would otherwise hide.
// A proper shared context is step 5's job; keeping both in one component is the
// smaller thing that keeps them honest until then.
function ThemeControls() {
  const { theme, mode, setTheme, toggleMode } = useTheme();
  const label = mode === "dark" ? "Switch to light mode" : "Switch to dark mode";
  const themes = Object.values(THEMES);

  return (
    <div className="flex items-center gap-2">
      {themes.length > 1 && (
        <Select
          size="toolbar"
          value={theme.id}
          onChange={(e) => setTheme(e.target.value)}
          aria-label="Theme"
        >
          {themes.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>
      )}
      <Button variant="icon" onClick={toggleMode} title={label} aria-label={label}>
        {mode === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
      </Button>
    </div>
  );
}

export function Header({ session }: HeaderProps) {
  if (!session) {
    return (
      <header className="flex items-center justify-between h-14 px-6 border-b border-app-border bg-app-bg">
        <Text variant="prose" as="h1" muted className="text-sm font-medium">
          minimal-agent
        </Text>
        <ThemeControls />
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
        <ThemeControls />
      </div>
    </header>
  );
}
