import { apiFetch } from "./client";

/** One registered agent, as reported by GET /config. */
export interface AgentConfig {
  name: string;
  display_name: string;
  workspace_root: string | null;
  model: string;
  backend: string;
  tools: string[];
}

export interface ServerConfig {
  version: string;
  agents: AgentConfig[];
  /** Set when exactly one agent is registered. */
  default_agent: string | null;
}

export async function getConfig(): Promise<ServerConfig> {
  const res = await apiFetch("/config");
  return res.json();
}
