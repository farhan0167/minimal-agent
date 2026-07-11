"""Two agents, one App, one process.

Run with `python my_app.py` (needs `mini-agent-kit[server]` installed and an
API key in the environment or a `.env` file — see the README). Opens an API
plus the bundled chat UI at http://localhost:8000; the UI's new-session
dialog lets you pick between the two agents.

Reasoning ("thinking") is opt-in and provider-specific. Set the
REASONING_* vars in your .env to match your backend and both agents will
stream their thinking trace to the chat UI (rendered as a collapsible
"Reasoning" block above each answer). Leave them unset for no reasoning.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from minimal_agent import Agent, App
from minimal_agent.config import settings
from minimal_agent.llm import LLM
from minimal_agent.llm.types import ReasoningConfig
from minimal_agent.tools.builtin.edit_file import EditFile
from minimal_agent.tools.builtin.glob import Glob
from minimal_agent.tools.builtin.grep import Grep
from minimal_agent.tools.builtin.read_file import ReadFile
from minimal_agent.tools.builtin.run_shell import RunShell
from minimal_agent.tools.builtin.spawn_agents import SpawnAgents
from minimal_agent.tools.builtin.web_extract import WebExtract
from minimal_agent.tools.builtin.web_search import WebSearch
from minimal_agent.tools.builtin.write_file import WriteFile

# Load .env into the process environment so the REASONING_* vars below are
# visible to os.environ (pydantic-settings reads .env into `settings`, but not
# into os.environ, and these vars are app-level rather than framework config).
load_dotenv()

workspace = Path.cwd()

llm = LLM(
    model=settings.LLM_MODEL,
    backend=settings.LLM_BACKEND,
    timeout=settings.OPENAI_TIMEOUT,
    max_retries=settings.OPENAI_MAX_RETRIES,
)


def build_reasoning() -> ReasoningConfig | None:
    """Build a ReasoningConfig from the REASONING_* env vars, or None.

    Reasoning is opt-in and provider-specific, so the request toggle and the
    response field are declared by you, the builder — not hard-coded here.
    Whether to reason, and how hard, is decided per run (agent.run / the web
    toolbar), so this config carries only the on-switch and the effort's SHAPE
    — never a static effort value.

      REASONING_REQUEST_KEY     a static on-switch request param, if the
                                provider needs one (e.g. "enable_thinking")
      REASONING_REQUEST_VALUE   its value; parsed as JSON (e.g. true),
                                falling back to the raw string. Do NOT put an
                                effort here — effort is per-run.
      REASONING_RESPONSE_FIELD  the field the trace comes back on
                                (e.g. "reasoning_content", "reasoning")
      REASONING_EFFORT_PARAM    the flat request key the per-run effort level
                                is written to. Optional; defaults to OpenAI's
                                "reasoning_effort", which OpenRouter accepts
                                too — set it only for a localhost dialect.

    Unset REASONING_RESPONSE_FIELD → reasoning off (returns None).
    """
    response_field = os.environ.get("REASONING_RESPONSE_FIELD")
    if not response_field:
        return None

    request_params: dict = {}
    key = os.environ.get("REASONING_REQUEST_KEY")
    if key:
        raw = os.environ.get("REASONING_REQUEST_VALUE", "")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        request_params[key] = value

    config_kwargs: dict = {
        "request_params": request_params,
        "response_field": response_field,
    }
    effort_param = os.environ.get("REASONING_EFFORT_PARAM")
    if effort_param:
        config_kwargs["effort_param"] = effort_param

    return ReasoningConfig(**config_kwargs)


reasoning_config = build_reasoning()


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
    return Agent(
        llm=llm,
        tools=[*tools, spawn_agents],
        workspace_root=workspace,
        reasoning_config=reasoning_config,
    )


def build_research_agent() -> Agent:
    """Researcher: web search plus read-only file access."""
    tools = [
        ReadFile(workspace_root=workspace, read_timestamps={}),
        Grep(workspace_root=workspace),
        Glob(workspace_root=workspace),
        WebSearch(),
        WebExtract(),
    ]
    return Agent(
        llm=llm,
        tools=tools,
        workspace_root=workspace,
        reasoning_config=reasoning_config,
    )


app = App(
    agents={
        "swe": build_swe_agent(),
        "research": build_research_agent(),
    }
)

if __name__ == "__main__":
    app.serve()
