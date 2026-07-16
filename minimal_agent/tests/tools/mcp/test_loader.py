"""mcp.json loader tests — format parsing, ${VAR} expansion, error paths."""

import json
import sys
from pathlib import Path

import pytest

from minimal_agent.tools import ToolContext
from minimal_agent.tools.mcp import (
    MCPPassthroughInput,
    MCPServerHTTP,
    MCPServerStdio,
    MCPToolProvider,
    load_mcp_servers,
)

from .test_provider import FIXTURE_SERVER


def _write(tmp_path: Path, document: dict) -> Path:
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps(document))
    return path


# -- Parsing ------------------------------------------------------------------


def test_parses_marketplace_style_stdio_entry(tmp_path):
    path = _write(
        tmp_path,
        {
            "mcpServers": {
                "notionApi": {
                    "command": "npx",
                    "args": ["-y", "@notionhq/notion-mcp-server"],
                    "env": {"OPENAPI_MCP_HEADERS": "{}"},
                }
            }
        },
    )
    (server,) = load_mcp_servers(path)
    assert server == MCPServerStdio(
        name="notionApi",
        command="npx",
        args=["-y", "@notionhq/notion-mcp-server"],
        env={"OPENAPI_MCP_HEADERS": "{}"},
    )


def test_parses_http_entry(tmp_path):
    path = _write(
        tmp_path,
        {
            "mcpServers": {
                "linear": {
                    "url": "https://mcp.linear.app/mcp",
                    "headers": {"Authorization": "Bearer x"},
                }
            }
        },
    )
    (server,) = load_mcp_servers(path)
    assert server == MCPServerHTTP(
        name="linear",
        url="https://mcp.linear.app/mcp",
        headers={"Authorization": "Bearer x"},
    )


def test_require_permission_extension_forwarded(tmp_path):
    path = _write(
        tmp_path,
        {"mcpServers": {"fs": {"command": "npx", "require_permission": False}}},
    )
    (server,) = load_mcp_servers(path)
    assert server.require_permission is False


def test_trust_read_only_hints_extension_forwarded(tmp_path):
    path = _write(
        tmp_path,
        {"mcpServers": {"fs": {"command": "npx", "trust_read_only_hints": True}}},
    )
    (server,) = load_mcp_servers(path)
    assert server.trust_read_only_hints is True


def test_read_only_hints_untrusted_by_default(tmp_path):
    """A pasted-in marketplace snippet gets the safe setting, unasked."""
    path = _write(tmp_path, {"mcpServers": {"fs": {"command": "npx"}}})
    (server,) = load_mcp_servers(path)
    assert server.trust_read_only_hints is False


def test_matching_type_field_accepted(tmp_path):
    path = _write(
        tmp_path,
        {
            "mcpServers": {
                "a": {"command": "x", "type": "stdio"},
                "b": {"url": "http://h/mcp", "type": "streamable-http"},
            }
        },
    )
    assert len(load_mcp_servers(path)) == 2


# -- ${VAR} expansion ---------------------------------------------------------


def test_env_var_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "ntn_secret")
    path = _write(
        tmp_path,
        {
            "mcpServers": {
                "notion": {
                    "url": "https://mcp.notion.com/mcp",
                    "headers": {"Authorization": "Bearer ${NOTION_TOKEN}"},
                }
            }
        },
    )
    (server,) = load_mcp_servers(path)
    assert server.headers == {"Authorization": "Bearer ntn_secret"}


def test_unset_env_var_fails_fast(tmp_path, monkeypatch):
    monkeypatch.delenv("DEFINITELY_UNSET_VAR", raising=False)
    path = _write(
        tmp_path,
        {
            "mcpServers": {
                "s": {"command": "x", "env": {"KEY": "${DEFINITELY_UNSET_VAR}"}}
            }
        },
    )
    with pytest.raises(ValueError, match="DEFINITELY_UNSET_VAR"):
        load_mcp_servers(path)


# -- Error paths --------------------------------------------------------------


def test_missing_file_names_expected_shape(tmp_path):
    with pytest.raises(FileNotFoundError, match="mcpServers"):
        load_mcp_servers(tmp_path / "absent.json")


def test_invalid_json_rejected(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text("{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_mcp_servers(path)


def test_missing_mcp_servers_key_rejected(tmp_path):
    path = _write(tmp_path, {"servers": {}})
    with pytest.raises(ValueError, match="mcpServers"):
        load_mcp_servers(path)


def test_entry_with_both_command_and_url_rejected(tmp_path):
    path = _write(tmp_path, {"mcpServers": {"s": {"command": "x", "url": "http://h"}}})
    with pytest.raises(ValueError, match="exactly one"):
        load_mcp_servers(path)


def test_entry_with_neither_command_nor_url_rejected(tmp_path):
    path = _write(tmp_path, {"mcpServers": {"s": {"args": ["x"]}}})
    with pytest.raises(ValueError, match="exactly one"):
        load_mcp_servers(path)


def test_mismatched_type_field_rejected(tmp_path):
    path = _write(tmp_path, {"mcpServers": {"s": {"command": "x", "type": "http"}}})
    with pytest.raises(ValueError, match="does not match"):
        load_mcp_servers(path)


# -- from_json ----------------------------------------------------------------


async def test_provider_from_json_end_to_end(tmp_path, monkeypatch):
    script = tmp_path / "fixture_server.py"
    script.write_text(FIXTURE_SERVER)
    monkeypatch.setenv("FIXTURE_SCRIPT", str(script))
    path = _write(
        tmp_path,
        {
            "mcpServers": {
                "fixture": {
                    "command": sys.executable,
                    "args": ["${FIXTURE_SCRIPT}"],
                }
            }
        },
    )
    async with MCPToolProvider.from_json(path) as tools:
        assert [t.name for t in tools] == ["mcp__fixture__add"]
        out = await tools[0].invoke(MCPPassthroughInput(a=20, b=22), ToolContext())
        assert tools[0].render_result_for_assistant(out) == "42"
