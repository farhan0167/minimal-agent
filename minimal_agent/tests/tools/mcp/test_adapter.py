"""MCPToolAdapter tests — schema projection, rendering, dispatch pipeline.

All tests run against a real in-memory MCP server (FastMCP over the SDK's
memory transport): no subprocesses, no network, but the full protocol.
"""

import base64
from contextlib import asynccontextmanager

import pytest
from mcp.server.fastmcp import FastMCP, Image
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import ToolAnnotations

from minimal_agent.llm.types import ToolCall
from minimal_agent.tools import ToolContext
from minimal_agent.tools.dispatcher import dispatch
from minimal_agent.tools.mcp import (
    MCPPassthroughInput,
    MCPToolAdapter,
    MCPToolError,
)

PNG_BYTES = b"not-really-a-png"


def _server() -> FastMCP:
    server = FastMCP("demo")

    @server.tool(description="Echo text back.")
    def echo(text: str) -> str:
        return f"echo: {text}"

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def peek() -> str:
        return "peeked"

    @server.tool()
    def boom() -> str:
        raise RuntimeError("kaboom")

    @server.tool()
    def screenshot() -> Image:
        return Image(data=PNG_BYTES, format="png")

    return server


@asynccontextmanager
async def connected_adapters(**adapter_kwargs):
    """(adapter, descriptor) per remote tool, over a live in-memory session.

    A context manager rather than a fixture: the memory transport's anyio
    cancel scope must enter and exit in the same task, and pytest-asyncio
    runs async-fixture setup and teardown in different tasks.
    """
    async with create_connected_server_and_client_session(
        _server()._mcp_server
    ) as session:
        listing = await session.list_tools()
        yield {
            tool.name: (
                MCPToolAdapter(
                    session=session, server_name="demo", tool=tool, **adapter_kwargs
                ),
                tool,
            )
            for tool in listing.tools
        }


async def test_name_is_namespaced():
    async with connected_adapters() as adapters:
        adapter, _ = adapters["echo"]
        assert adapter.name == "mcp__demo__echo"


async def test_as_llm_tool_ships_server_schema_verbatim():
    async with connected_adapters() as adapters:
        adapter, descriptor = adapters["echo"]
        wire = adapter.as_llm_tool()
        assert wire.name == "mcp__demo__echo"
        assert wire.description == "Echo text back."
        assert wire.parameters == descriptor.inputSchema


async def test_invoke_returns_text_result():
    async with connected_adapters() as adapters:
        adapter, _ = adapters["echo"]
        out = await adapter.invoke(MCPPassthroughInput(text="hi"), ToolContext())
        assert adapter.render_result_for_assistant(out) == "echo: hi"
        assert adapter.render_parts_for_assistant(out) == []


async def test_is_error_raises_mcp_tool_error():
    async with connected_adapters() as adapters:
        adapter, _ = adapters["boom"]
        with pytest.raises(MCPToolError, match="kaboom"):
            await adapter.invoke(MCPPassthroughInput(), ToolContext())


async def test_dispatcher_pipeline_end_to_end():
    async with connected_adapters() as adapters:
        tools_by_name = {a.name: a for a, _ in adapters.values()}

        msg, parts = await dispatch(
            ToolCall(id="c1", name="mcp__demo__echo", arguments={"text": "hi"}),
            tools_by_name,
            ToolContext(),
        )
        assert msg.content == "echo: hi"
        assert parts == []

        # isError routes through the dispatcher's exception path, not a lying OK.
        msg, _ = await dispatch(
            ToolCall(id="c2", name="mcp__demo__boom", arguments={}),
            tools_by_name,
            ToolContext(),
        )
        assert msg.content.startswith("tool error: MCPToolError")


async def test_read_only_hint_does_not_disarm_permission_by_default():
    """The server's hint is reported, but it can't waive the host's prompt.

    Otherwise a server could skip its own permission check by stamping a
    destructive tool readOnlyHint=True.
    """
    async with connected_adapters() as adapters:
        read_only, _ = adapters["peek"]
        assert read_only.is_read_only is True
        assert read_only.needs_permission(MCPPassthroughInput()) is True

        mutating, _ = adapters["echo"]
        assert mutating.is_read_only is False
        assert mutating.needs_permission(MCPPassthroughInput()) is True


async def test_trusted_read_only_hint_skips_prompt():
    """Opting in is what lets a read-only tool through unprompted."""
    async with connected_adapters(trust_read_only_hints=True) as adapters:
        read_only, _ = adapters["peek"]
        assert read_only.needs_permission(MCPPassthroughInput()) is False

        # Trusting hints only relaxes tools that actually carry one.
        mutating, _ = adapters["echo"]
        assert mutating.needs_permission(MCPPassthroughInput()) is True


async def test_require_permission_false_disables_prompting():
    async with connected_adapters(require_permission=False) as adapters:
        adapter, _ = adapters["echo"]
        assert adapter.needs_permission(MCPPassthroughInput()) is False


async def test_permission_description_names_server_and_tool():
    async with connected_adapters() as adapters:
        adapter, _ = adapters["echo"]
        description = adapter.permission_description(MCPPassthroughInput(text="hi"))
        assert "echo" in description
        assert "demo" in description


async def test_image_result_relocates_as_data_uri_part():
    async with connected_adapters() as adapters:
        adapter, _ = adapters["screenshot"]
        out = await adapter.invoke(MCPPassthroughInput(), ToolContext())

        parts = adapter.render_parts_for_assistant(out)
        assert len(parts) == 1
        expected_b64 = base64.b64encode(PNG_BYTES).decode()
        assert parts[0].image_url.url == f"data:image/png;base64,{expected_b64}"

        # The tool message itself carries the mandatory text pointer.
        pointer = adapter.render_result_for_assistant(out)
        assert "attached as the following message" in pointer


async def test_passthrough_input_accepts_arbitrary_arguments():
    args = MCPPassthroughInput.model_validate({"anything": 1, "goes": ["here"]})
    assert args.model_dump() == {"anything": 1, "goes": ["here"]}
