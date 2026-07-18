"""A research agent, served in the browser.

Web search plus read-only file access — no writing, no shell. Run it with:

    uv run main.py        # → http://localhost:8000

Set your API key in the environment (or a .env file in this directory) first —
see .env.example.

MCP servers declared in `.minimal_agent/mcp.json` (the standard `mcpServers`
format) are connected at startup and their tools handed to the agent.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from minimal_agent import LLM, Agent, App
from minimal_agent.llm import ReasoningConfig
from minimal_agent.tools.builtin import (
    Glob,
    Grep,
    ReadFile,
    WebExtract,
    WebSearch,
    WriteFile,
    EditFile,
)
from minimal_agent.tools.mcp import MCPToolProvider

load_dotenv()

workspace = Path.cwd()

# The behavior prompt shapes the agent's identity — here, a read-only researcher.
# Resolved relative to this file so it's found no matter where you run from.
behavior = Path(__file__).parent / "behavior.md"

# Reasoning ("thinking") is opt-in and provider-specific: you declare how it's
# requested and where the trace comes back. This shape is for OpenRouter, which
# returns the trace on the `reasoning` field. Delete this and drop
# `reasoning_config` below if your model or backend doesn't reason.
reasoning = ReasoningConfig(response_field="reasoning")

llm = LLM(
    model=os.environ.get("LLM_MODEL", "qwen/qwen3.7-plus"),
    backend=os.environ.get("LLM_BACKEND", "openrouter"),
    api_key=os.environ["OPENROUTER_API_KEY"],
    reasoning_config=reasoning,
)


async def main():
    # from_json() reads .minimal_agent/mcp.json (e.g. a Notion server) and
    # fails fast if it's missing; ${VAR} references in the file are expanded
    # from the environment at load time. The provider owns the MCP server
    # connections and must stay open for the agent's whole life, so the app
    # is constructed and served inside the block — with the async `a_serve()`,
    # because the blocking `app.serve()` would try to own its own event loop.
    # One dict, shared by all three file tools: read_file records what it has
    # read here, and edit_file/write_file consult it for the read-before-edit
    # guard. Separate dicts would mean reads never satisfy the guard and
    # edit_file rejects every call with "File has not been read yet".
    read_timestamps: dict[str, float] = {}

    async with MCPToolProvider.from_json() as mcp_tools:
        agent = Agent(
            llm=llm,
            tools=[
                ReadFile(workspace_root=workspace, read_timestamps=read_timestamps),
                Grep(workspace_root=workspace),
                Glob(workspace_root=workspace),
                WebSearch(),
                WebExtract(),
                EditFile(workspace_root=workspace, read_timestamps=read_timestamps),
                WriteFile(workspace_root=workspace, read_timestamps=read_timestamps),
                *mcp_tools,  # e.g. mcp__notionApi__* from .minimal_agent/mcp.json
            ],
            prompt=behavior,
            workspace_root=workspace,
        )
        app = App(agents=agent)
        await app.a_serve()


if __name__ == "__main__":
    asyncio.run(main())
