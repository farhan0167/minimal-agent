/**
 * Tool UI registrations.
 *
 * assistant-ui hides tool-call parts that have no registered UI.
 * To ensure every tool renders, we register a generic ToolCallRenderer
 * for each known tool name.
 *
 * Tool names are fetched from the server via GET /tools.
 */
import { makeAssistantToolUI } from "@assistant-ui/react";
import { ToolCallRenderer } from "./ToolCallRenderer";

/** Build assistant-ui tool UIs dynamically from server-provided names. */
export function buildToolUIs(toolNames: string[]) {
  return toolNames.map((name) =>
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
}
