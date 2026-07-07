import { apiFetch } from "./client";

export interface ToolInfo {
  name: string;
}

interface ToolListResponse {
  tools: ToolInfo[];
}

export async function getTools(agent?: string | null): Promise<ToolInfo[]> {
  const query = agent ? `?agent=${encodeURIComponent(agent)}` : "";
  const res = await apiFetch(`/tools${query}`);
  const data: ToolListResponse = await res.json();
  return data.tools;
}
