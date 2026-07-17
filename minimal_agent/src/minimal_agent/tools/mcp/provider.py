"""`MCPToolProvider` — owns MCP server connections, yields ready tools.

An async context manager. On enter: connect every configured server, run
the MCP handshake, snapshot `tools/list`, and build one `MCPToolAdapter`
per remote tool. On exit: close every session and subprocess. Adapters are
only valid inside the `async with` block — the host keeps the provider open
for the agent's whole life. See
[.claude/specifications/mcp-integration.md](../../../.claude/specifications/mcp-integration.md).
"""

from contextlib import AsyncExitStack
from pathlib import Path
from typing import List, Optional, Sequence, Union

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from .adapter import MCPToolAdapter
from .config import MCPServerConfig, MCPServerStdio
from .loader import DEFAULT_MCP_CONFIG_PATH, load_mcp_servers


class MCPToolProvider:
    """Connects to MCP servers and hands the agent plain tool instances.

    Connection failures raise out of `__aenter__` (after closing whatever
    did connect) — broken wiring surfaces at startup, not mid-run. The
    toolset is a snapshot: `tools/list` runs once per server at connect;
    `tools/list_changed` notifications are ignored.
    """

    def __init__(self, servers: Sequence[MCPServerConfig]) -> None:
        names = [s.name for s in servers]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"duplicate MCP server names: {sorted(duplicates)}")
        self._servers = list(servers)
        self._stack: Optional[AsyncExitStack] = None

    @classmethod
    def from_json(
        cls, path: Union[str, Path] = DEFAULT_MCP_CONFIG_PATH
    ) -> "MCPToolProvider":
        """Build a provider from an `mcpServers` JSON file.

        The format is the ecosystem-standard one MCP marketplaces publish
        (see [loader.py](loader.py)); the default location is
        `.minimal_agent/mcp.json`.
        """
        return cls(load_mcp_servers(path))

    async def __aenter__(self) -> List[MCPToolAdapter]:
        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            adapters: List[MCPToolAdapter] = []
            for config in self._servers:
                session = await self._connect(stack, config)
                listing = await session.list_tools()
                adapters.extend(
                    MCPToolAdapter(
                        session=session,
                        server_name=config.name,
                        tool=tool,
                        require_permission=config.require_permission,
                        trust_read_only_hints=config.trust_read_only_hints,
                    )
                    for tool in listing.tools
                )
        except BaseException:
            await stack.aclose()
            raise
        self._stack = stack
        return adapters

    async def __aexit__(self, *exc) -> None:
        if self._stack is not None:
            stack, self._stack = self._stack, None
            await stack.__aexit__(*exc)

    @staticmethod
    async def _connect(stack: AsyncExitStack, config: MCPServerConfig) -> ClientSession:
        """Open one server's transport + session on the shared exit stack."""
        if isinstance(config, MCPServerStdio):
            transport = stdio_client(
                StdioServerParameters(
                    command=config.command,
                    args=config.args,
                    env=config.env or None,
                )
            )
            read, write = await stack.enter_async_context(transport)
        else:
            transport = streamablehttp_client(
                config.url, headers=config.headers or None
            )
            read, write, _get_session_id = await stack.enter_async_context(transport)
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        return session
