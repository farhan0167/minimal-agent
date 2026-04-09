"""The ``web_search`` tool — search the web via Tavily Search API."""

from minimal_agent.tools.base import BaseTool
from minimal_agent.tools.builtin._tavily import tavily_request
from minimal_agent.tools.context import ToolContext

from .schema import WebSearchInput


class WebSearch(BaseTool[WebSearchInput, dict]):
    name = "web_search"
    input_schema = WebSearchInput
    is_read_only = True

    async def invoke(self, args: WebSearchInput, ctx: ToolContext) -> dict:
        payload: dict = {
            "query": args.query,
            "search_depth": args.search_depth,
            "max_results": args.max_results,
            "topic": args.topic,
            "include_answer": args.include_answer,
            "include_raw_content": args.include_raw_content,
        }
        if args.time_range is not None:
            payload["time_range"] = args.time_range

        return await tavily_request("/search", payload)

    def needs_permission(self, args: WebSearchInput) -> bool:
        return True

    def permission_description(self, args: WebSearchInput) -> str:
        q = args.query if len(args.query) <= 80 else args.query[:77] + "..."
        return f"Web search: {q}"

    def render_result_for_assistant(self, out: dict) -> str:
        parts: list[str] = []

        if out.get("answer"):
            parts.append(f"**Answer:** {out['answer']}\n")

        results = out.get("results", [])
        if not results:
            parts.append("No results found.")
            return "\n".join(parts)

        for i, r in enumerate(results, 1):
            title = r.get("title", "Untitled")
            url = r.get("url", "")
            content = r.get("content", "")
            parts.append(f"[{i}] {title}")
            parts.append(f"    {url}")
            if content:
                parts.append(f"    {content}")
            raw = r.get("raw_content")
            if raw:
                # Truncate raw content to keep context manageable
                preview = raw[:2000]
                if len(raw) > 2000:
                    preview += "\n... (truncated)"
                parts.append(f"    --- Full content ---\n{preview}")
            parts.append("")

        return "\n".join(parts)
