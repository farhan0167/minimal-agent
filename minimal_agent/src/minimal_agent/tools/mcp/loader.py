"""Load MCP server configs from the ecosystem-standard `mcpServers` JSON.

The format is the one MCP marketplaces publish and Claude Desktop / Cursor /
VS Code read, so a server's install snippet pastes in unchanged:

    {
      "mcpServers": {
        "notionApi": {
          "command": "npx",
          "args": ["-y", "@notionhq/notion-mcp-server"],
          "env": {"NOTION_TOKEN": "${NOTION_TOKEN}"}
        },
        "linear": {
          "url": "https://mcp.linear.app/mcp",
          "headers": {"Authorization": "Bearer ${LINEAR_TOKEN}"}
        }
      }
    }

An entry with `command` is stdio; one with `url` is streamable HTTP. String
values may reference environment variables as `${VAR}` — expanded at load
time, failing fast if unset — so secrets live in the environment/.env, never
in the checked-in file. The non-standard keys `require_permission` (default
true) and `trust_read_only_hints` (default false) are our extensions,
forwarded to the server config. The default location is
`.minimal_agent/mcp.json`, beside the default sessions dir. See
[.claude/specifications/mcp-integration.md](../../../.claude/specifications/mcp-integration.md).
"""

import json
import os
import re
from pathlib import Path
from typing import List, Union

from .config import MCPServerConfig, MCPServerHTTP, MCPServerStdio

DEFAULT_MCP_CONFIG_PATH = Path(".minimal_agent/mcp.json")

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

# `type` values seen in marketplace snippets, normalized per transport.
_STDIO_TYPES = {"stdio"}
_HTTP_TYPES = {"http", "streamable-http", "streamable_http"}


def _expand(value: str, *, server: str) -> str:
    """Substitute ${VAR} from the environment; unset variables fail fast."""

    def replace(match: re.Match) -> str:
        var = match.group(1)
        expanded = os.environ.get(var)
        if expanded is None:
            raise ValueError(
                f"mcp.json server {server!r}: environment variable {var!r} "
                f"is not set (referenced as ${{{var}}})"
            )
        return expanded

    return _VAR_RE.sub(replace, value)


def _expand_dict(values: dict, *, server: str) -> dict:
    return {k: _expand(v, server=server) for k, v in values.items()}


def _parse_server(name: str, entry: dict, *, source: Path) -> MCPServerConfig:
    if not isinstance(entry, dict):
        raise ValueError(f"{source}: server {name!r} must be a JSON object")

    has_command = "command" in entry
    has_url = "url" in entry
    if has_command == has_url:
        raise ValueError(
            f"{source}: server {name!r} must have exactly one of "
            "'command' (stdio) or 'url' (streamable HTTP)"
        )

    declared = entry.get("type")
    if declared is not None:
        expected = _STDIO_TYPES if has_command else _HTTP_TYPES
        if declared not in expected:
            raise ValueError(
                f"{source}: server {name!r} declares type {declared!r}, which "
                f"does not match its "
                f"{'command (stdio)' if has_command else 'url (streamable HTTP)'} "
                "transport"
            )

    require_permission = bool(entry.get("require_permission", True))
    trust_read_only_hints = bool(entry.get("trust_read_only_hints", False))

    if has_command:
        return MCPServerStdio(
            name=name,
            command=_expand(entry["command"], server=name),
            args=[_expand(a, server=name) for a in entry.get("args", [])],
            env=_expand_dict(entry.get("env", {}), server=name),
            require_permission=require_permission,
            trust_read_only_hints=trust_read_only_hints,
        )
    return MCPServerHTTP(
        name=name,
        url=_expand(entry["url"], server=name),
        headers=_expand_dict(entry.get("headers", {}), server=name),
        require_permission=require_permission,
        trust_read_only_hints=trust_read_only_hints,
    )


def load_mcp_servers(
    path: Union[str, Path] = DEFAULT_MCP_CONFIG_PATH,
) -> List[MCPServerConfig]:
    """Parse an `mcpServers` JSON file into server configs.

    Raises FileNotFoundError if the file is absent, ValueError on a
    malformed document — broken wiring surfaces at startup, matching
    `MCPToolProvider`'s fail-fast connect.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"MCP config file not found: {path} — create it with an "
            '{"mcpServers": {...}} object, or pass servers programmatically'
        )
    try:
        document = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON: {e}") from e

    servers = document.get("mcpServers") if isinstance(document, dict) else None
    if not isinstance(servers, dict):
        raise ValueError(f"{path} must contain a top-level 'mcpServers' object")

    return [_parse_server(name, entry, source=path) for name, entry in servers.items()]
