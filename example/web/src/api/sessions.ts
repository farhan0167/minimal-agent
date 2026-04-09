import type {
  CreateSessionRequest,
  Session,
  SessionListResponse,
} from "../types/session";
import { apiFetch } from "./client";

export async function createSession(
  req: CreateSessionRequest,
): Promise<Session> {
  const res = await apiFetch("/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return res.json();
}

export async function listSessions(): Promise<Session[]> {
  const res = await apiFetch("/sessions");
  const data: SessionListResponse = await res.json();
  return data.sessions;
}

export async function getSession(sessionId: string): Promise<Session> {
  const res = await apiFetch(`/sessions/${sessionId}`);
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiFetch(`/sessions/${sessionId}`, { method: "DELETE" });
}
