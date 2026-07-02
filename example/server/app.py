"""Session wiring and workspace validation — agent logic delegated to agents/."""

import json
import os
from pathlib import Path

from agents import get_agent_config
from minimal_agent.agent import Agent, Session
from minimal_agent.config import settings


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


def get_sessions_dir() -> Path:
    return Path(settings.SESSIONS_DIR)


# --- Agent type sidecar ---


def save_agent_type(session_id: str, agent_type: str) -> None:
    """Write agent_type.json sidecar next to session.json."""
    sidecar = get_sessions_dir() / session_id / "agent_type.json"
    sidecar.write_text(json.dumps({"agent_type": agent_type}))


def load_agent_type(session_id: str) -> str:
    """Read agent type from sidecar file."""
    sidecar = get_sessions_dir() / session_id / "agent_type.json"
    if not sidecar.exists():
        raise FileNotFoundError(f"agent_type.json not found for session {session_id}")
    data = json.loads(sidecar.read_text())
    return data["agent_type"]


# --- Session lifecycle ---


def build_agent(
    agent_type: str,
    workspace: Path,
    model: str | None = None,
    backend: str | None = None,
) -> Agent:
    """Build an agent by delegating to the appropriate agent module."""
    agent_config = get_agent_config(agent_type)
    return agent_config.build_agent(workspace, model=model, backend=backend)


async def create_session(
    workspace: Path,
    agent_type: str,
    model: str | None = None,
    backend: str | None = None,
) -> Session:
    """Create a new session bound to a workspace and agent type."""
    model = model or settings.LLM_MODEL
    backend = backend or settings.LLM_BACKEND

    agent = build_agent(agent_type, workspace, model=model, backend=backend)
    session = await agent.create_session(base_dir=get_sessions_dir())

    save_agent_type(session.session_id, agent_type)

    return session


async def resume_session(session_id: str) -> tuple[Agent, Session]:
    """Rebuild a session's agent and resume it with identity re-attached.

    The agent is constructed to match the session's persisted
    model/backend/workspace; agent.load_session() then rebuilds the
    system prompt fresh and validates that everything agrees. This is
    the path for running the agent against an existing session.
    """
    meta = Session.read_meta(session_id, base_dir=get_sessions_dir())
    if meta.workspace_root is None:
        raise ValueError(f"Session {session_id} has no workspace_root")
    workspace = validate_workspace(meta.workspace_root)

    agent_type = load_agent_type(session_id)
    agent = build_agent(
        agent_type, workspace, model=meta.model, backend=meta.backend
    )
    session = await agent.load_session(session_id, base_dir=get_sessions_dir())
    return agent, session


def open_session_readonly(session_id: str) -> Session:
    """Load a session for inspection only (metadata + stored messages).

    Deliberately promptless: read-only consumers serialize the stored
    conversation and never run the agent, so get_messages() should not
    contain a system message. To run the agent, use resume_session().
    """
    meta = Session.read_meta(session_id, base_dir=get_sessions_dir())
    return Session.load(
        session_id,
        model=meta.model,
        backend=meta.backend,
        system_prompt=None,
        base_dir=get_sessions_dir(),
    )
