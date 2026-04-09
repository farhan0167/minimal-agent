"""The ``web_extract`` tool — extract page content via Tavily Extract API."""

from ...base import BaseTool
from ...context import ToolContext
from .._tavily import tavily_request
from .schema import WebExtractInput

_MAX_CONTENT_CHARS = 5000


class WebExtract(BaseTool[WebExtractInput, dict]):
    name = "web_extract"
    input_schema = WebExtractInput
    is_read_only = True

    async def invoke(self, args: WebExtractInput, ctx: ToolContext) -> dict:
        payload: dict = {
            "urls": args.urls,
            "extract_depth": args.extract_depth,
            "format": args.format,
        }
        if args.query is not None:
            payload["query"] = args.query

        return await tavily_request("/extract", payload)

    def needs_permission(self, args: WebExtractInput) -> bool:
        return True

    def permission_description(self, args: WebExtractInput) -> str:
        n = len(args.urls)
        if n == 1:
            url = args.urls[0]
            if len(url) > 70:
                url = url[:67] + "..."
            return f"Extract content from: {url}"
        return f"Extract content from {n} URLs"

    def render_result_for_assistant(self, out: dict) -> str:
        parts: list[str] = []

        results = out.get("results", [])
        failed = out.get("failed_results", [])

        if not results and not failed:
            return "No content extracted."

        for r in results:
            url = r.get("url", "")
            raw = r.get("raw_content", "")
            parts.append(f"## {url}")
            if raw:
                preview = raw[:_MAX_CONTENT_CHARS]
                if len(raw) > _MAX_CONTENT_CHARS:
                    preview += f"\n... (truncated, {len(raw):,} chars total)"
                parts.append(preview)
            else:
                parts.append("(no content)")
            parts.append("")

        for f in failed:
            url = f.get("url", "")
            error = f.get("error", "unknown error")
            parts.append(f"FAILED: {url} — {error}")

        return "\n".join(parts)
