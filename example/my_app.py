"""Two agents, one App, one process.

Run with `python my_app.py` (needs `mini-agent-kit[server]` installed and an
API key in the environment or a `.env` file — see the README). Opens an API
plus the bundled chat UI at http://localhost:8000; the UI's new-session
dialog lets you pick between the two agents.
"""

from pathlib import Path

from minimal_agent import Agent, App
from minimal_agent.config import settings
from minimal_agent.llm import LLM
from minimal_agent.tools.builtin.edit_file import EditFile
from minimal_agent.tools.builtin.glob import Glob
from minimal_agent.tools.builtin.grep import Grep
from minimal_agent.tools.builtin.read_file import ReadFile
from minimal_agent.tools.builtin.run_shell import RunShell
from minimal_agent.tools.builtin.spawn_agents import SpawnAgents
from minimal_agent.tools.builtin.web_extract import WebExtract
from minimal_agent.tools.builtin.web_search import WebSearch
from minimal_agent.tools.builtin.write_file import WriteFile

workspace = Path.cwd()

llm = LLM(
    model=settings.LLM_MODEL,
    backend=settings.LLM_BACKEND,
    timeout=settings.OPENAI_TIMEOUT,
    max_retries=settings.OPENAI_MAX_RETRIES,
)


def build_swe_agent() -> Agent:
    """Software engineer: full read/write/shell toolset plus sub-agents."""
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
    spawn_agents = SpawnAgents(
        llm=llm,
        available_tools={t.name: t for t in tools},
        workspace_root=workspace,
    )
    return Agent(llm=llm, tools=[*tools, spawn_agents], workspace_root=workspace)


def build_research_agent() -> Agent:
    """Researcher: web search plus read-only file access."""
    tools = [
        ReadFile(workspace_root=workspace, read_timestamps={}),
        Grep(workspace_root=workspace),
        Glob(workspace_root=workspace),
        WebSearch(),
        WebExtract(),
    ]
    return Agent(llm=llm, tools=tools, workspace_root=workspace)


app = App(
    agents={
        "swe": build_swe_agent(),
        "research": build_research_agent(),
    }
)

if __name__ == "__main__":
    app.serve()
