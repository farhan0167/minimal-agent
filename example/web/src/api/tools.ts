import { apiFetch } from "./client";

export interface ToolInfo {
  name: string;
}

interface ToolListResponse {
  tools: ToolInfo[];
}

export async function getTools(agentType: string): Promise<ToolInfo[]> {
  const res = await apiFetch(`/tools?agent_type=${encodeURIComponent(agentType)}`);
  const data: ToolListResponse = await res.json();
  return data.tools;
}
