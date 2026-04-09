import { API_BASE_URL } from "../lib/constants";

/**
 * Thin wrapper around fetch that prepends the API base URL
 * and handles JSON error responses.
 */
export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const url = `${API_BASE_URL}${path}`;
  const response = await fetch(url, init);

  if (!response.ok && response.headers.get("content-type")?.includes("json")) {
    const body = await response.json();
    throw new ApiError(response.status, body.detail ?? "Unknown error");
  }

  if (!response.ok) {
    throw new ApiError(response.status, response.statusText);
  }

  return response;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}
