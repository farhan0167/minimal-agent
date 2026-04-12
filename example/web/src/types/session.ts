export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface Session {
  session_id: string;
  workspace_root: string | null;
  agent_type: string;
  model: string;
  backend: string;
  created_at: string;
  updated_at: string;
  usage: Usage | null;
}

export interface CreateSessionRequest {
  workspace_root: string;
  agent_type: string;
  model?: string;
  backend?: string;
}

export interface SessionListResponse {
  sessions: Session[];
}
