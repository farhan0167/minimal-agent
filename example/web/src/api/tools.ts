import { apiFetch } from "./client";

export interface ToolInfo {
  name: string;
}

interface ToolListResponse {
  tools: ToolInfo[];
}

export async function getTools(): Promise<ToolInfo[]> {
  const res = await apiFetch("/tools");
  const data: ToolListResponse = await res.json();
  return data.tools;
}
