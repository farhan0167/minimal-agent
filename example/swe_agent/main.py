"""A software-engineer agent, served in the browser.

Full read/write/shell toolset plus sub-agent spawning. Run it with:

    uv run main.py        # → http://localhost:8000

Set your API key in the environment (or a .env file in this directory) first —
see .env.example.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from minimal_agent import LLM, Agent, App
from minimal_agent.tools.builtin import (
    EditFile,
    Glob,
    Grep,
    ReadFile,
    RunShell,
    SpawnAgents,
    WebExtract,
    WebSearch,
    WriteFile,
)

load_dotenv()

workspace = Path.cwd()

llm = LLM(
    model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
    backend=os.environ.get("LLM_BACKEND", "openai"),
    api_key=os.environ["OPENAI_API_KEY"],
)

# One read-timestamps map shared across the read/edit/write tools so edits and
# writes can tell whether a file was read (and hasn't changed) since.
read_timestamps: dict[str, float] = {}

tools = [
    ReadFile(workspace_root=workspace, read_timestamps=read_timestamps),
    EditFile(workspace_root=workspace, read_timestamps=read_timestamps),
    WriteFile(workspace_root=workspace, read_timestamps=read_timestamps),
    RunShell(workspace_root=workspace),
    Grep(workspace_root=workspace),
    Glob(workspace_root=workspace),
    WebSearch(),
    WebExtract(),
]

# The spawn_agents tool fans work out to concurrent sub-agents, each with the
# same toolset, all recorded under this session.
spawn_agents = SpawnAgents(
    llm=llm,
    available_tools={tool.name: tool for tool in tools},
    workspace_root=workspace,
)

agent = Agent(
    llm=llm,
    tools=[*tools, spawn_agents],
    workspace_root=workspace,
)

app = App(agents=agent)

if __name__ == "__main__":
    app.serve()
