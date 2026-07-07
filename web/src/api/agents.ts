import { apiFetch } from "./client";

export interface AgentInfo {
  name: string;
  display_name: string;
}

interface AgentListResponse {
  agents: AgentInfo[];
}

export async function listAgents(): Promise<AgentInfo[]> {
  const res = await apiFetch("/agents");
  const data: AgentListResponse = await res.json();
  return data.agents;
}
