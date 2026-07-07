export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface Session {
  session_id: string;
  workspace_root: string | null;
  /** Registered agent name; null if the sidecar is missing. */
  agent: string | null;
  model: string;
  backend: string;
  created_at: string;
  updated_at: string;
  usage: Usage | null;
}

export interface CreateSessionRequest {
  /** Optional when the server has exactly one registered agent. */
  agent?: string;
}

export interface SessionListResponse {
  sessions: Session[];
}
