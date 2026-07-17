import type { ThemeManifest } from "./types";

/**
 * The claude theme's manifest. Values live in claude.css; these are the
 * companions no stylesheet can set.
 *
 * github-light/github-dark and Mermaid's default/dark are what the app has
 * always used — they were literals in ShikiHighlighter and MermaidBlock. They
 * are the claude theme's choice now, not the app's.
 */
export const claude: ThemeManifest = {
  id: "claude",
  name: "Claude",
  shiki: { light: "github-light", dark: "github-dark" },
  mermaid: { light: "default", dark: "dark" },
};
