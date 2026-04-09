/**
 * Tool UI registrations.
 *
 * assistant-ui hides tool-call parts that have no registered UI.
 * To ensure every tool renders, we register a generic ToolCallRenderer
 * for each known tool name.
 *
 * To add a new tool: just add its name to TOOL_NAMES below.
 */
import { makeAssistantToolUI } from "@assistant-ui/react";
import { ToolCallRenderer } from "./ToolCallRenderer";

/** All tool names the server may produce. */
const TOOL_NAMES = [
  "read_file",
  "write_file",
  "edit_file",
  "run_shell",
  "grep",
  "glob",
  "web_search",
  "web_extract",
  "get_weather",
  "spawn_agents",
] as const;

/** Generate a makeAssistantToolUI component for each tool name. */
export const toolUIs = TOOL_NAMES.map((name) =>
  makeAssistantToolUI({
    toolName: name,
    render: ({ args, result, status }) => (
      <ToolCallRenderer
        name={name}
        args={args as Record<string, unknown>}
        result={result}
        status={status.type === "running" ? "running" : "complete"}
      />
    ),
  }),
);
