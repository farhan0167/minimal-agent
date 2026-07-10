/**
 * Map file extensions to Shiki language ids, for highlighting file contents
 * inside tool-call cards. Unknown extensions fall back to "text" (rendered
 * unhighlighted by ShikiSyntaxHighlighter).
 */
const LANGUAGE_BY_EXTENSION: Record<string, string> = {
  js: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  jsx: "jsx",
  ts: "typescript",
  mts: "typescript",
  cts: "typescript",
  tsx: "tsx",
  py: "python",
  rb: "ruby",
  go: "go",
  rs: "rust",
  java: "java",
  kt: "kotlin",
  swift: "swift",
  c: "c",
  h: "c",
  cc: "cpp",
  cpp: "cpp",
  cxx: "cpp",
  hpp: "cpp",
  cs: "csharp",
  php: "php",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  fish: "fish",
  ps1: "powershell",
  sql: "sql",
  html: "html",
  htm: "html",
  css: "css",
  scss: "scss",
  less: "less",
  json: "json",
  jsonc: "jsonc",
  yaml: "yaml",
  yml: "yaml",
  toml: "toml",
  ini: "ini",
  xml: "xml",
  svg: "xml",
  md: "markdown",
  mdx: "mdx",
  tex: "latex",
  vue: "vue",
  svelte: "svelte",
  dockerfile: "dockerfile",
  makefile: "makefile",
  lua: "lua",
  r: "r",
  scala: "scala",
  dart: "dart",
  ex: "elixir",
  exs: "elixir",
  erl: "erlang",
  hs: "haskell",
  zig: "zig",
  diff: "diff",
  patch: "diff",
};

const LANGUAGE_BY_FILENAME: Record<string, string> = {
  dockerfile: "dockerfile",
  makefile: "makefile",
};

/** Infer a Shiki language id from a file path. */
export function languageForPath(path: string): string {
  const basename = path.split("/").pop()?.toLowerCase() ?? "";
  if (LANGUAGE_BY_FILENAME[basename]) return LANGUAGE_BY_FILENAME[basename];
  const ext = basename.includes(".") ? basename.split(".").pop()! : "";
  return LANGUAGE_BY_EXTENSION[ext] ?? "text";
}
