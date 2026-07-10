import { useSyncExternalStore } from "react";

/**
 * Client-side session titles, derived from the first user message.
 *
 * The backend has no title field on sessions, so titles live in localStorage,
 * keyed by session id. A tiny external store lets the sidebar re-render when
 * a title is derived while the chat panel loads history or sends the first
 * message.
 */
const STORAGE_KEY = "minimal-agent.session-titles";
const MAX_TITLE_LENGTH = 60;

function load(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

let titles: Record<string, string> = load();
const listeners = new Set<() => void>();

function persist() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(titles));
  listeners.forEach((listener) => listener());
}

export function getSessionTitle(sessionId: string): string | undefined {
  return titles[sessionId];
}

export function setSessionTitle(sessionId: string, title: string) {
  const trimmed = title.replace(/\s+/g, " ").trim().slice(0, MAX_TITLE_LENGTH);
  if (!trimmed || titles[sessionId] === trimmed) return;
  titles = { ...titles, [sessionId]: trimmed };
  persist();
}

export function removeSessionTitle(sessionId: string) {
  if (!(sessionId in titles)) return;
  titles = Object.fromEntries(
    Object.entries(titles).filter(([id]) => id !== sessionId),
  );
  persist();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Reactive title for one session; undefined until a first message exists. */
export function useSessionTitle(sessionId: string): string | undefined {
  return useSyncExternalStore(subscribe, () => titles[sessionId]);
}
