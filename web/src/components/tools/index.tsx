/**
 * Tool UI registrations.
 *
 * assistant-ui hides tool-call parts that have no registered UI.
 * To ensure every tool renders, we register a UI for each known tool name
 * (fetched from the server via GET /tools): a dedicated renderer from
 * registry.ts when one exists, else the generic ToolCallRenderer.
 */
import { makeAssistantToolUI } from "@assistant-ui/react";
import type { ToolCallMessagePartStatus } from "@assistant-ui/react";
import { ToolCallRenderer, type ToolStatus } from "./ToolCallRenderer";
import { TOOL_RENDERERS } from "./registry";

// The backend reports tool failures as plain strings with a stable prefix
// rather than a structured flag — one prefix per exit in the dispatch
// pipeline (see minimal_agent tools/dispatcher.py _dispatch_inner).
const ERROR_RESULT_PREFIX =
  /^(error|invalid arguments|validation failed|permission error|permission denied|tool error):/;

function toToolStatus(
  status: ToolCallMessagePartStatus,
  result: unknown,
): ToolStatus {
  if (status.type === "running" || status.type === "requires-action") {
    return "running";
  }
  if (status.type === "incomplete") {
    return status.reason === "cancelled" ? "interrupted" : "error";
  }
  if (typeof result === "string" && ERROR_RESULT_PREFIX.test(result)) {
    return "error";
  }
  return "complete";
}

/** Build assistant-ui tool UIs dynamically from server-provided names. */
export function buildToolUIs(toolNames: string[]) {
  return toolNames.map((name) => {
    const Renderer = TOOL_RENDERERS[name] ?? ToolCallRenderer;
    return makeAssistantToolUI({
      toolName: name,
      render: ({ args, result, status }) => (
        <Renderer
          name={name}
          args={args as Record<string, unknown>}
          result={result}
          status={toToolStatus(status, result)}
        />
      ),
    });
  });
}
