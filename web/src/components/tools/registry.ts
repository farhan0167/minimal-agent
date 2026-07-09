import type { FC } from "react";
import type { ToolRenderProps } from "./types";
import { ReadFileRenderer } from "./renderers/ReadFile";
import { WriteFileRenderer } from "./renderers/WriteFile";
import { EditFileRenderer } from "./renderers/EditFile";
import { RunShellRenderer } from "./renderers/RunShell";
import { SearchRenderer } from "./renderers/Search";
import { WebSearchRenderer } from "./renderers/WebSearch";
import { WebExtractRenderer } from "./renderers/WebExtract";

/**
 * Tool name → dedicated renderer. Tools not listed here fall back to the
 * generic ToolCallRenderer (args JSON + raw result).
 *
 * See web/README.md — "Writing a renderer for a new tool".
 */
export const TOOL_RENDERERS: Record<string, FC<ToolRenderProps>> = {
  read_file: ReadFileRenderer,
  write_file: WriteFileRenderer,
  edit_file: EditFileRenderer,
  run_shell: RunShellRenderer,
  grep: SearchRenderer,
  glob: SearchRenderer,
  web_search: WebSearchRenderer,
  web_extract: WebExtractRenderer,
};
