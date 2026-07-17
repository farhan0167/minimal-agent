import type { ThemeManifest } from "./types";
import { claude } from "./claude";
import { graphite } from "./graphite";

/**
 * The theme registry.
 *
 * Adding a theme: write themes/<id>.css filling the contract, write its
 * manifest, import both here. That is the whole change — the floors above
 * read roles, so nothing else knows a theme exists.
 *
 * The CSS is imported here rather than in index.css so a theme is never
 * half-registered: the file that names it is the file that loads it.
 */
import "./claude.css";
import "./graphite.css";

export const THEMES: Record<string, ThemeManifest> = {
  [claude.id]: claude,
  [graphite.id]: graphite,
};

/** The theme a first-time visitor gets, and the fallback for an unknown id. */
export const DEFAULT_THEME_ID = claude.id;

export type ThemeId = string;

/**
 * Resolves an id to a manifest, falling back to the default.
 *
 * A stored id can outlive the theme it names (a rename, a removed theme, a
 * hand-edited localStorage), and a missing manifest would otherwise surface as
 * an unstyled app or a crash on `.shiki`. Falling back keeps a stale value from
 * becoming a broken session.
 */
export function resolveTheme(id: string | null | undefined): ThemeManifest {
  return (id && THEMES[id]) || THEMES[DEFAULT_THEME_ID];
}

export type { ThemeManifest } from "./types";
