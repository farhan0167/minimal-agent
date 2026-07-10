import { useCallback, useEffect, useState } from "react";
import type { CreateSessionRequest, Session } from "../types/session";
import * as sessionsApi from "../api/sessions";
import { removeSessionTitle } from "../lib/session-titles";

const ACTIVE_SESSION_KEY = "minimal-agent.active-session";

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
  const [activeSessionId, setActiveSessionId] = useState<string | null>(() =>
    localStorage.getItem(ACTIVE_SESSION_KEY),
  );
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Survive page refreshes: remember the selection across visits.
  useEffect(() => {
    if (activeSessionId) {
      localStorage.setItem(ACTIVE_SESSION_KEY, activeSessionId);
    } else {
      localStorage.removeItem(ACTIVE_SESSION_KEY);
    }
  }, [activeSessionId]);

  const activeSession =
    sessions.find((s) => s.session_id === activeSessionId) ?? null;

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const list = await sessionsApi.listSessions();
      setSessions(list);
      // Drop a restored selection that no longer exists server-side.
      setActiveSessionId((prev) =>
        prev && list.some((s) => s.session_id === prev) ? prev : null,
      );
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
      removeSessionTitle(sessionId);
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
