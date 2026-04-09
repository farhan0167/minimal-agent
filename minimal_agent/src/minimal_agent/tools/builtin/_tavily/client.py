"""Shared HTTP client for Tavily API calls."""

import httpx

from ....config import settings

_TAVILY_BASE_URL = "https://api.tavily.com"
_TIMEOUT = 30.0


async def tavily_request(endpoint: str, payload: dict) -> dict:
    """POST to a Tavily API endpoint and return the JSON response.

    Raises ``TavilyError`` on HTTP or API errors.
    """
    api_key = settings.TAVILY_API_KEY
    if not api_key:
        raise TavilyError("TAVILY_API_KEY is not set. Add it to your .env file.")

    url = f"{_TAVILY_BASE_URL}/{endpoint.lstrip('/')}"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    if resp.status_code != 200:
        detail = resp.text[:300]
        raise TavilyError(f"Tavily API error (HTTP {resp.status_code}): {detail}")

    return resp.json()


class TavilyError(Exception):
    """Raised when a Tavily API call fails."""
