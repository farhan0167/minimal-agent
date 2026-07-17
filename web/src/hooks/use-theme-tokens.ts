import { useSyncExternalStore } from "react";
import { resolveTheme } from "../themes";
import type { ThemeManifest } from "../themes";
import type { Mode } from "./use-theme";

function subscribe(callback: () => void) {
  const observer = new MutationObserver(callback);
  observer.observe(document.documentElement, {
    attributes: true,
    // Both axes: .dark rides on class, identity on data-theme.
    attributeFilter: ["class", "data-theme"],
  });
  return () => observer.disconnect();
}

function readMode(): Mode {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

function readThemeId(): string {
  return document.documentElement.dataset.theme ?? "";
}

/**
 * The active theme and mode, read from the DOM.
 *
 * Generalizes the old useIsDark. Unlike useTheme — which owns the state — this
 * observes <html>, so it stays correct no matter which component instance
 * changed things, and works for consumers that only need to *read*.
 *
 * It exists for the two renderers that can't read --app-*: Shiki compiles a
 * named theme into inline styles, Mermaid draws to SVG. They need the manifest,
 * not tokens, which is exactly what this returns.
 *
 * useSyncExternalStore requires a referentially stable snapshot — returning a
 * fresh {theme, mode} object each call would loop forever. So the two axes are
 * subscribed separately and both snapshots are primitives (a manifest is
 * identity-stable from the registry; the mode is a string).
 */
export function useThemeTokens(): { theme: ThemeManifest; mode: Mode } {
  const mode = useSyncExternalStore(subscribe, readMode);
  const themeId = useSyncExternalStore(subscribe, readThemeId);
  return { theme: resolveTheme(themeId), mode };
}
