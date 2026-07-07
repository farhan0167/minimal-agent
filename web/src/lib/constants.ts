/**
 * Base URL for the FastAPI server.
 *
 * In development, Vite proxies /api/* to localhost:8000 (see vite.config.ts).
 * In production, set VITE_API_BASE_URL to the server's URL.
 */
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "/api";
