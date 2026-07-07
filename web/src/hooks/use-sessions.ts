import { useCallback, useEffect, useState } from "react";
import type { CreateSessionRequest, Session } from "../types/session";
import * as sessionsApi from "../api/sessions";

interface UseSessionsReturn {
  sessions: Session[];
  activeSession: Session | null;
  isLoading: boolean;
  error: string | null;
  createSession: (req: CreateSessionRequest) => Promise<Session>;
  selectSession: (sessionId: string) => void;
  removeSession: (sessionId: string) => Promise<void>;
  refresh: () => Promise<void>;
}

export function useSessions(): UseSessionsReturn {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const activeSession =
    sessions.find((s) => s.session_id === activeSessionId) ?? null;

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const list = await sessionsApi.listSessions();
      setSessions(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sessions");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const createSession = useCallback(
    async (req: CreateSessionRequest): Promise<Session> => {
      const session = await sessionsApi.createSession(req);
      setSessions((prev) => [session, ...prev]);
      setActiveSessionId(session.session_id);
      return session;
    },
    [],
  );

  const selectSession = useCallback((sessionId: string) => {
    setActiveSessionId(sessionId);
  }, []);

  const removeSession = useCallback(
    async (sessionId: string) => {
      await sessionsApi.deleteSession(sessionId);
      setSessions((prev) =>
        prev.filter((s) => s.session_id !== sessionId),
      );
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
      }
    },
    [activeSessionId],
  );

  return {
    sessions,
    activeSession,
    isLoading,
    error,
    createSession,
    selectSession,
    removeSession,
    refresh,
  };
}
