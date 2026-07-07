"""Two agents, one App, one process.

Run with `python my_app.py` (needs `mini-agent-kit[server]` installed and an
API key in the environment or a `.env` file — see the README). Opens an API
plus the bundled chat UI at http://localhost:8000; the UI's new-session
dialog lets you pick between the two agents.

Phoenix tracing (optional): set `PHOENIX=1` in the environment (and install
`mini-agent-kit[phoenix]` plus a running Phoenix at localhost:6006) to export
every run's spans. Leave it unset and the app runs exactly as before.
"""

import atexit
import os
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


def build_phoenix_sinks() -> list:
    """A PhoenixSink exporting to a local Phoenix, when PHOENIX=1 is set.

    Off by default so the example runs without the `phoenix` extra. When on,
    the sink streams OpenTelemetry spans for every run (and sub-agent) to
    Phoenix at localhost:6006, and is flushed at process exit.
    """
    if os.getenv("PHOENIX") != "1":
        return []

    from minimal_agent.observability import PhoenixSink

    # PHOENIX_FULL=1 also flattens each call's reconstructed input (system
    # prompt + messages) onto the LLM span, so Phoenix shows what the model
    # saw — at the cost of a per-call blob read and sending prompt content
    # off-box. Off by default: references + timing + tokens only.
    full = os.getenv("PHOENIX_FULL") == "1"
    sink = PhoenixSink.for_local(project_name="minimal-agent-example", full=full)
    atexit.register(sink.shutdown)  # drain buffered spans on a clean exit
    print(f"Phoenix tracing on → http://localhost:6006 (full input: {full})")
    return [sink]


app = App(
    agents={
        "swe": build_swe_agent(),
        "research": build_research_agent(),
    },
    extra_sinks=build_phoenix_sinks(),
)

if __name__ == "__main__":
    app.serve()
