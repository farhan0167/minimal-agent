import { useCallback, useEffect, useState } from "react";
import { resolveTheme } from "../themes";
import type { ThemeManifest } from "../themes";

// Still "minimal-agent.theme" though it now holds only the mode: this key has
// light/dark in real browsers. Renaming it to match the new vocabulary would
// silently reset every existing user's choice — a stale name is cheaper than
// that surprise.
const MODE_KEY = "minimal-agent.theme";
const THEME_KEY = "minimal-agent.theme-id";

/** Light or dark — which half of a theme is showing. */
export type Mode = "light" | "dark";

/**
 * Theme identity and mode: two independent axes.
 *
 * `theme` is which palette (claude, graphite…); `mode` is light or dark within
 * it. They persist separately because they answer different questions —
 * switching theme should not reset your light/dark choice, and vice versa.
 *
 * Mode follows the OS preference until the user picks explicitly. Theme has no
 * OS signal, so it starts at the registry's default.
 *
 * Both are applied to <html>: data-theme for identity, .dark for mode. The
 * theme CSS, the @theme bridge and the vendor aliases all key off those two.
 */
export function useTheme() {
  const [mode, setMode] = useState<Mode>(() => {
    const stored = localStorage.getItem(MODE_KEY);
    if (stored === "light" || stored === "dark") return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  });

  // Resolved, not trusted: a stored id can name a theme that no longer exists
  // (a rename, a removal, a hand-edited localStorage), and an unknown
  // data-theme leaves every token unfilled.
  const [theme, setThemeState] = useState<ThemeManifest>(() =>
    resolveTheme(localStorage.getItem(THEME_KEY)),
  );

  useEffect(() => {
    document.documentElement.classList.toggle("dark", mode === "dark");
  }, [mode]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme.id;
  }, [theme]);

  // Track OS mode changes, but only while the user hasn't chosen explicitly.
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (localStorage.getItem(MODE_KEY)) return;
      setMode(mq.matches ? "dark" : "light");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const toggleMode = useCallback(() => {
    setMode((current) => {
      const next = current === "dark" ? "light" : "dark";
      localStorage.setItem(MODE_KEY, next);
      return next;
    });
  }, []);

  const setTheme = useCallback((id: string) => {
    const resolved = resolveTheme(id);
    localStorage.setItem(THEME_KEY, resolved.id);
    setThemeState(resolved);
  }, []);

  return { theme, mode, setTheme, toggleMode };
}
