import type { ThemeManifest } from "./types";

/**
 * The blueprint theme's manifest. Values live in blueprint.css; these are the
 * companions no stylesheet can set.
 *
 * Blueprint is monochrome by conviction, so its code should be too: Shiki's
 * `min-light`/`min-dark` are the most chroma-starved bundles — near-grayscale
 * with a single blue for emphasis, which is exactly the drafting register.
 * Mermaid's `neutral` keeps diagrams grayscale for the same reason.
 */
export const blueprint: ThemeManifest = {
  id: "blueprint",
  name: "Blueprint",
  shiki: { light: "min-light", dark: "min-dark" },
  mermaid: { light: "neutral", dark: "dark" },
};
