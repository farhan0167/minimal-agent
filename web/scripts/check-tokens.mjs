#!/usr/bin/env node
/*
 * The floor guard.
 *
 * Values live in themes/, roles live in tokens.css, raw utilities live in
 * components/ui/. Everywhere else composes primitives and names roles. This
 * script is what keeps that true by construction rather than by care.
 *
 * Ran warn-only while the primitive floor was built; the last call site was
 * converted with the eight primitives, so it now fails the build. A guard that
 * warns is a guard that gets ignored — the point of reaching zero was to earn
 * the right to hold it.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("../src", import.meta.url).pathname;
const WARN_ONLY = false;

// Paths allowed to speak in literals, and why.
const EXEMPT = [
  "components/ui/", // the primitive floor: the only home of raw utilities
  "themes/", // values live here by definition
  "tokens.css", // the contract itself
  "index.css", // the @theme bridge + the quarantined vendor block
];

/**
 * Blanks out comment spans in one line, carrying /* … *\/ state across lines.
 *
 * Deliberately not a parser: it does not know about strings, so a "//" inside a
 * string literal blanks the rest of the line. That direction is safe — it can
 * only hide a violation from a guard that is advisory anyway, never invent one
 * — and the alternative is tokenising TS/CSS to answer a grep.
 */
function stripComments(line, inBlockComment) {
  let text = "";
  let i = 0;
  while (i < line.length) {
    if (inBlockComment) {
      const end = line.indexOf("*/", i);
      if (end === -1) return { text, inBlockComment: true };
      inBlockComment = false;
      i = end + 2;
      continue;
    }
    if (line.startsWith("//", i)) break;
    if (line.startsWith("/*", i)) {
      inBlockComment = true;
      i += 2;
      continue;
    }
    text += line[i++];
  }
  return { text, inBlockComment };
}

const RULES = [
  {
    id: "raw-hex",
    // A literal colour, e.g. #ae5630 — belongs in a theme, not a component.
    // Restricted to CSS's real hex lengths; "#27" was never a colour.
    re: /#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b/g,
    msg: "raw hex colour — add a token to tokens.css and read it via the bridge",
  },
  {
    id: "tailwind-palette",
    // Tailwind's stock palette, e.g. bg-zinc-900 — bypasses the contract, so
    // it cannot respond to a theme.
    re: /\b(?:bg|text|border|ring|from|to|via|divide|outline)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b/g,
    msg: "Tailwind palette class — use an --app-* role (e.g. bg-app-surface)",
  },
  {
    id: "arbitrary-token",
    // The old bg-[hsl(var(--x))] spelling the @theme bridge replaces.
    re: /\[hsl\(var\(/g,
    msg: "arbitrary-value token syntax — the bridge means you can write bg-app-*",
  },
  {
    id: "font-literal",
    // The theme's voice is --app-font-prose, not a class sprinkled per file.
    re: /\bfont-serif\b/g,
    msg: "font-serif literal — prose voice is --app-font-prose (font-prose)",
  },
];

const files = [];
(function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full);
    else if (/\.(tsx?|css)$/.test(full)) files.push(full);
  }
})(ROOT);

let violations = 0;
for (const file of files) {
  const rel = relative(ROOT, file);
  if (EXEMPT.some((e) => rel.startsWith(e) || rel === e)) continue;

  const lines = readFileSync(file, "utf8").split("\n");
  // Tracks /* … */ regions across lines so a rule can't fire inside one.
  let inBlockComment = false;

  lines.forEach((line, i) => {
    // Comments are prose: they ship nothing to the browser, so a literal in one
    // is not a violation. "#185" (an issue reference) is shaped exactly like a
    // 3-digit hex colour, and no regex can tell them apart — the difference is
    // the context, so the scanner has to strip it rather than out-clever it.
    const code = stripComments(line, inBlockComment);
    inBlockComment = code.inBlockComment;
    if (!code.text.trim()) return;

    for (const rule of RULES) {
      rule.re.lastIndex = 0;
      const hit = rule.re.exec(code.text);
      if (!hit) continue;
      violations++;
      console.log(
        `  ${rel}:${i + 1}  ${hit[0]}\n      ${rule.id}: ${rule.msg}`,
      );
    }
  });
}

if (violations === 0) {
  console.log("token floor: clean — no literals outside ui/ and themes/");
  process.exit(0);
}
console.log(
  `\ntoken floor: ${violations} violation(s) in ${files.length} files scanned`,
);
if (WARN_ONLY) {
  console.log("(warn-only while the primitive floor is being built)");
  process.exit(0);
}
process.exit(1);
