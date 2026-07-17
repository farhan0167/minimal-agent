/**
 * What a theme must declare.
 *
 * The CSS file fills the token contract; this manifest carries the parts a
 * stylesheet cannot reach. Shiki and Mermaid render to their own colour systems
 * — Shiki compiles a named theme into inline styles, Mermaid draws to SVG — so
 * neither can read --app-*. Naming their companions here keeps the choice with
 * the theme rather than hardcoded in ShikiHighlighter and MermaidBlock, where
 * no theme could reach it.
 *
 * Adding a theme is this file's shape, one CSS file, and a line in the
 * registry. Nothing above the themes floor changes.
 */

/** Shiki's bundled theme names. Both modes, because Shiki compiles both. */
export interface ShikiThemes {
  light: string;
  dark: string;
}

/**
 * Mermaid's built-in theme names ("default" is its light one).
 *
 * Mirrors mermaid's own union rather than widening to string: a typo here would
 * otherwise surface as a diagram silently rendering in the wrong palette, and
 * the set is fixed by the library, not by us.
 */
export type MermaidTheme =
  | "default"
  | "base"
  | "dark"
  | "forest"
  | "neutral"
  | "neo"
  | "neo-dark"
  | "redux"
  | "redux-dark"
  | "redux-color"
  | "redux-dark-color"
  | "null";

export interface MermaidThemes {
  light: MermaidTheme;
  dark: MermaidTheme;
}

export interface ThemeManifest {
  /** Stamped as <html data-theme="…">; the CSS file's selector must match. */
  id: string;
  /** Human-facing name, for the theme picker step 5 will add. */
  name: string;
  shiki: ShikiThemes;
  mermaid: MermaidThemes;
}
