"""Agent and session wiring — workspace validation, agent construction."""

import os
from pathlib import Path

from minimal_agent.agent import Agent, Session
from minimal_agent.config import settings
from minimal_agent.llm import LLM
from minimal_agent.tools.builtin.edit_file import EditFile
from minimal_agent.tools.builtin.get_weather import GetWeather
from minimal_agent.tools.builtin.glob import Glob
from minimal_agent.tools.builtin.grep import Grep
from minimal_agent.tools.builtin.read_file import ReadFile
from minimal_agent.tools.builtin.run_shell import RunShell
from minimal_agent.tools.builtin.spawn_agents import SpawnAgents
from minimal_agent.tools.builtin.web_extract import WebExtract
from minimal_agent.tools.builtin.web_search import WebSearch
from minimal_agent.tools.builtin.write_file import WriteFile


def get_allowed_workspaces() -> list[str] | None:
    """Parse ALLOWED_WORKSPACES env var into a list of directory prefixes."""
    raw = os.environ.get("ALLOWED_WORKSPACES")
    if not raw:
        return None
    return [p.strip() for p in raw.split(",") if p.strip()]


def validate_workspace(workspace_root: str) -> Path:
    """Validate and return a resolved workspace path.

    Raises ValueError if the path is invalid or not allowed.
    """
    path = Path(workspace_root)

    if not path.is_absolute():
        raise ValueError(f"workspace_root must be an absolute path: {workspace_root}")

    path = path.resolve()

    if not path.exists():
        raise ValueError(f"workspace_root does not exist: {path}")

    if not path.is_dir():
        raise ValueError(f"workspace_root is not a directory: {path}")

    allowed = get_allowed_workspaces()
    if allowed is not None:
        if not any(str(path).startswith(prefix) for prefix in allowed):
            raise ValueError(
                f"workspace_root is not in the allowed workspaces: {path}"
            )

    return path


def get_tool_names() -> list[str]:
    """Return the names of all tools the server registers, without instantiation."""
    tool_classes = [
        GetWeather,
        ReadFile,
        EditFile,
        WriteFile,
        RunShell,
        Grep,
        Glob,
        WebSearch,
        WebExtract,
        SpawnAgents,
    ]
    return [cls.name for cls in tool_classes]


def build_agent(workspace: Path) -> Agent:
    """Construct the default agent with all builtin tools for a workspace."""
    llm = LLM(
        model=settings.LLM_MODEL,
        backend=settings.LLM_BACKEND,
        timeout=settings.OPENAI_TIMEOUT,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )

    read_timestamps: dict[str, float] = {}

    builtin_tools = [
        GetWeather(),
        ReadFile(workspace_root=workspace, read_timestamps=read_timestamps),
        EditFile(workspace_root=workspace, read_timestamps=read_timestamps),
        WriteFile(workspace_root=workspace, read_timestamps=read_timestamps),
        RunShell(workspace_root=workspace),
        Grep(workspace_root=workspace),
        Glob(workspace_root=workspace),
        WebSearch(),
        WebExtract(),
    ]

    tools_by_name = {t.name: t for t in builtin_tools}

    spawn_agents = SpawnAgents(
        llm=llm,
        available_tools=tools_by_name,
        workspace_root=workspace,
    )

    return Agent(
        llm=llm,
        tools=[*builtin_tools, spawn_agents],
    )


def get_sessions_dir() -> Path:
    return Path(settings.SESSIONS_DIR)


async def create_session(
    workspace: Path,
    model: str | None = None,
    backend: str | None = None,
) -> Session:
    """Create a new session bound to a workspace."""
    model = model or settings.LLM_MODEL
    backend = backend or settings.LLM_BACKEND

    agent = build_agent(workspace)
    system_prompt = await agent.build_system_prompt(workspace_root=workspace)

    return Session.create(
        model=model,
        backend=backend,
        system_prompt=system_prompt,
        base_dir=get_sessions_dir(),
        workspace_root=str(workspace),
    )


def load_session(session_id: str) -> Session:
    """Load an existing session from disk."""
    sessions_dir = get_sessions_dir()
    meta_path = sessions_dir / session_id / "session.json"

    if not meta_path.exists():
        raise FileNotFoundError(f"Session not found: {session_id}")

    import json

    with open(meta_path) as f:
        data = json.load(f)

    return Session.load(
        session_id=session_id,
        model=data["model"],
        backend=data["backend"],
        system_prompt=None,
        base_dir=sessions_dir,
    )
