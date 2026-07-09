import type { ToolStatus } from "./ToolCallCard";

/**
 * Props every tool renderer receives — the registry in registry.ts maps
 * tool names to components of this shape.
 */
export interface ToolRenderProps {
  name: string;
  args: Record<string, unknown>;
  result: unknown;
  status: ToolStatus;
}
