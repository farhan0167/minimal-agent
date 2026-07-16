"""Server configuration dataclasses for MCP connections.

Pure data — this module deliberately imports nothing from the `mcp` SDK so
hosts can type-annotate their configs without forcing the optional extra. See
[.claude/specifications/mcp-integration.md](../../../.claude/specifications/mcp-integration.md)
for the design.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Union

# The server name becomes the first segment of every derived tool name
# (mcp__<server>__<tool>), so it must stay function-calling-safe.
_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise ValueError(
            f"MCP server name {name!r} must match [a-zA-Z0-9_-]+ — it is "
            "embedded in tool names shipped to the model."
        )


@dataclass(frozen=True)
class MCPServerStdio:
    """An MCP server run as a local subprocess over stdio."""

    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    # Tools from this server prompt through the session's
    # permission_callback. Hosts that trust the server set this False.
    require_permission: bool = True
    # Whether to believe the server's own readOnlyHint annotation and skip
    # the prompt for tools it declares harmless. Off by default: the hint is
    # an untrusted claim by the party being gated, so trusting it is the
    # host's call to make, not the server's. Turning it on for a chatty
    # read-only server is the intended use.
    trust_read_only_hints: bool = False

    def __post_init__(self) -> None:
        _validate_name(self.name)


@dataclass(frozen=True)
class MCPServerHTTP:
    """An MCP server reached over streamable HTTP."""

    name: str
    url: str
    headers: Dict[str, str] = field(default_factory=dict)
    require_permission: bool = True
    # See MCPServerStdio.trust_read_only_hints. Especially worth leaving off
    # here: a hosted server's annotations are controlled by its operator.
    trust_read_only_hints: bool = False

    def __post_init__(self) -> None:
        _validate_name(self.name)


MCPServerConfig = Union[MCPServerStdio, MCPServerHTTP]
