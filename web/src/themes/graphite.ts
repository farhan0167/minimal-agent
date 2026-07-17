import type { ThemeManifest } from "./types";

/**
 * The graphite theme's manifest. Values live in graphite.css; these are the
 * companions no stylesheet can set.
 *
 * Graphite's accent is ink, not colour, so its code wants the same restraint:
 * github's default pair is the most neutral Shiki bundles, and mermaid's
 * `neutral` is its grayscale theme — both keep diagrams and code from
 * reintroducing a hue the palette deliberately withholds.
 */
export const graphite: ThemeManifest = {
  id: "graphite",
  name: "Graphite",
  shiki: { light: "github-light-default", dark: "github-dark-default" },
  mermaid: { light: "neutral", dark: "dark" },
};
