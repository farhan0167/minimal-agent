"""`MCPToolAdapter` — one remote MCP tool projected onto `BaseTool`.

The adapter is a plain tool: the dispatcher pipeline, permission flow, and
observability apply to it unchanged, and nothing downstream can tell it is
remote. Identity (`name`, schema, read-only flag) is per-instance because it
is discovered from the server at connect time — the reason `BaseTool` allows
instance-level metadata. See
[.claude/specifications/mcp-integration.md](../../../.claude/specifications/mcp-integration.md).
"""

from mcp import ClientSession
from mcp import types as mcp_types
from pydantic import BaseModel, ConfigDict

from ...llm.types import ContentPart, ImagePart, ImageUrl, LLMTool
from ..base import BaseTool
from ..context import ToolContext


class MCPToolError(Exception):
    """A tool call the server answered with `isError: true`.

    Raised out of `invoke` so the dispatcher records `ToolStatus.ERROR`
    truthfully; the message body is the server's error text.
    """


class MCPPassthroughInput(BaseModel):
    """Accepts any argument dict; real validation is the server's job.

    The model never sees this schema — `MCPToolAdapter.as_llm_tool` ships
    the server's own JSON Schema verbatim. This model only satisfies the
    dispatcher's parse step without rejecting arguments the server allows.
    """

    model_config = ConfigDict(extra="allow")


def _render_text(content: list) -> str:
    """Join a result's text-bearing blocks; images ride the parts channel."""
    parts: list[str] = []
    for block in content:
        if isinstance(block, mcp_types.TextContent):
            parts.append(block.text)
        elif isinstance(block, mcp_types.ImageContent):
            continue
        elif isinstance(block, mcp_types.EmbeddedResource):
            text = getattr(block.resource, "text", None)
            parts.append(
                text
                if text is not None
                else f"[embedded resource: {block.resource.uri}]"
            )
        else:
            parts.append(f"[{block.type} content]")
    return "\n".join(parts)


class MCPToolAdapter(BaseTool[MCPPassthroughInput, mcp_types.CallToolResult]):
    input_schema = MCPPassthroughInput

    def __init__(
        self,
        session: ClientSession,
        server_name: str,
        tool: mcp_types.Tool,
        require_permission: bool = True,
        trust_read_only_hints: bool = False,
    ) -> None:
        # Double underscore separates segments because MCP tool names may
        # themselves contain single underscores.
        self.name = f"mcp__{server_name}__{tool.name}"
        self._remote_name = tool.name
        self._server_name = server_name
        self._schema = tool.inputSchema
        self._description = tool.description or ""
        self._session = session
        # Descriptive only — reports what the server claims, for gating and
        # observability. It deliberately does NOT decide whether we prompt:
        # readOnlyHint is an assertion by the party the prompt exists to
        # gate, so a server could disarm its own permission check by
        # stamping every tool read-only. The host opts into believing it.
        self.is_read_only = bool(tool.annotations and tool.annotations.readOnlyHint)
        self._require_permission = require_permission and not (
            trust_read_only_hints and self.is_read_only
        )

    def as_llm_tool(self) -> LLMTool:
        # The server's schema, verbatim — no Pydantic round-trip.
        return LLMTool(
            name=self.name,
            description=self._description,
            parameters=self._schema,
        )

    def needs_permission(self, args: MCPPassthroughInput) -> bool:
        return self._require_permission

    def permission_description(self, args: MCPPassthroughInput) -> str:
        return (
            f"Call MCP tool '{self._remote_name}' on server "
            f"'{self._server_name}' with {args.model_dump()}"
        )

    async def invoke(
        self, args: MCPPassthroughInput, ctx: ToolContext
    ) -> mcp_types.CallToolResult:
        result = await self._session.call_tool(self._remote_name, args.model_dump())
        if result.isError:
            raise MCPToolError(_render_text(result.content) or "MCP tool call failed")
        return result

    def render_result_for_assistant(self, out: mcp_types.CallToolResult) -> str:
        text = _render_text(out.content)
        n_images = sum(isinstance(b, mcp_types.ImageContent) for b in out.content)
        if n_images:
            pointer = f"{n_images} image(s) attached as the following message."
            return f"{text}\n{pointer}" if text else pointer
        return text

    def render_parts_for_assistant(
        self, out: mcp_types.CallToolResult
    ) -> list[ContentPart]:
        return [
            ImagePart(image_url=ImageUrl(url=f"data:{b.mimeType};base64,{b.data}"))
            for b in out.content
            if isinstance(b, mcp_types.ImageContent)
        ]
