"""minimal_agent.tools.mcp — MCP server tools as ordinary `BaseTool`s.

Requires the mcp extra: pip install "mini-agent-kit[mcp]".
"""

try:
    import mcp as _mcp  # noqa: F401
except ImportError as e:
    raise ImportError(
        'MCP support requires the mcp extra — pip install "mini-agent-kit[mcp]"'
    ) from e

from .adapter import MCPPassthroughInput, MCPToolAdapter, MCPToolError
from .config import MCPServerConfig, MCPServerHTTP, MCPServerStdio
from .loader import DEFAULT_MCP_CONFIG_PATH, load_mcp_servers
from .provider import MCPToolProvider

__all__ = [
    "DEFAULT_MCP_CONFIG_PATH",
    "MCPPassthroughInput",
    "MCPServerConfig",
    "MCPServerHTTP",
    "MCPServerStdio",
    "MCPToolAdapter",
    "MCPToolError",
    "MCPToolProvider",
    "load_mcp_servers",
]
