"""MCPToolProvider tests — config validation, discovery, lifecycle.

The end-to-end tests spawn a real FastMCP server as a stdio subprocess
(the fixture script below), exercising the same transport a production
stdio config uses.
"""

import importlib
import sys
from pathlib import Path

import pytest

from minimal_agent.tools import ToolContext
from minimal_agent.tools.mcp import (
    MCPPassthroughInput,
    MCPServerHTTP,
    MCPServerStdio,
    MCPToolProvider,
)

FIXTURE_SERVER = """
from mcp.server.fastmcp import FastMCP

server = FastMCP("fixture")


@server.tool(description="Add two integers.")
def add(a: int, b: int) -> int:
    return a + b


if __name__ == "__main__":
    server.run()
"""


@pytest.fixture
def server_script(tmp_path: Path) -> str:
    script = tmp_path / "fixture_server.py"
    script.write_text(FIXTURE_SERVER)
    return str(script)


# -- Config validation --------------------------------------------------------


def test_duplicate_server_names_rejected():
    servers = [
        MCPServerStdio(name="fs", command="x"),
        MCPServerHTTP(name="fs", url="http://localhost:1/mcp"),
    ]
    with pytest.raises(ValueError, match="duplicate"):
        MCPToolProvider(servers)


@pytest.mark.parametrize("bad_name", ["has space", "has__dots.", "", "a/b"])
def test_unsafe_server_name_rejected(bad_name):
    with pytest.raises(ValueError, match="a-zA-Z0-9_-"):
        MCPServerStdio(name=bad_name, command="x")


# -- Lifecycle ----------------------------------------------------------------


async def test_discovers_and_calls_over_stdio(server_script):
    async with MCPToolProvider(
        [MCPServerStdio(name="fixture", command=sys.executable, args=[server_script])]
    ) as tools:
        assert [t.name for t in tools] == ["mcp__fixture__add"]
        out = await tools[0].invoke(MCPPassthroughInput(a=2, b=3), ToolContext())
        assert tools[0].render_result_for_assistant(out) == "5"


async def test_multiple_servers_union_namespaced(server_script):
    async with MCPToolProvider(
        [
            MCPServerStdio(name="one", command=sys.executable, args=[server_script]),
            MCPServerStdio(name="two", command=sys.executable, args=[server_script]),
        ]
    ) as tools:
        assert sorted(t.name for t in tools) == ["mcp__one__add", "mcp__two__add"]


async def test_connect_failure_raises_from_aenter(server_script):
    provider = MCPToolProvider(
        [
            # A good server first, so the failure path must also unwind an
            # already-open connection.
            MCPServerStdio(name="good", command=sys.executable, args=[server_script]),
            MCPServerStdio(name="bad", command="/nonexistent-command-xyz"),
        ]
    )
    with pytest.raises(BaseException):  # noqa: B017 — transport error type is SDK detail
        async with provider:
            pytest.fail("__aenter__ must not succeed with an unreachable server")


# -- Extra guard --------------------------------------------------------------


def test_import_without_mcp_extra_gives_install_hint(monkeypatch):
    for mod in [m for m in sys.modules if m == "mcp" or m.startswith("mcp.")]:
        monkeypatch.delitem(sys.modules, mod)
    for mod in [m for m in sys.modules if m.startswith("minimal_agent.tools.mcp")]:
        monkeypatch.delitem(sys.modules, mod)
    # None in sys.modules makes `import mcp` raise ImportError at the guard.
    monkeypatch.setitem(sys.modules, "mcp", None)

    with pytest.raises(ImportError, match=r"mini-agent-kit\[mcp\]"):
        importlib.import_module("minimal_agent.tools.mcp")
