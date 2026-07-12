"""Session lifecycle against live registered agents.

The example server rebuilt agents per-request from config modules; here
the App holds live Agent instances, so lifecycle reduces to: resolve the
registry entry, delegate to the agent's own session factories, and keep
an agent_type.json sidecar so resumed sessions route back to the same
registry entry.
"""

import json

from ..agent import Agent, Session, SessionManager

DEFAULT_AGENT_NAME = "default"


class UnknownAgentError(LookupError):
    """The requested agent name is not in the registry."""


def resolve_agent(agents: dict[str, Agent], name: str | None) -> tuple[str, Agent]:
    """Return (name, agent) for the requested name.

    A None name is allowed only when exactly one agent is registered —
    the single-agent App shouldn't force clients to name it.
    """
    if name is None:
        if len(agents) == 1:
            return next(iter(agents.items()))
        raise UnknownAgentError(
            "Multiple agents are registered — specify one of: "
            + ", ".join(sorted(agents))
        )
    try:
        return name, agents[name]
    except KeyError:
        raise UnknownAgentError(
            f"Unknown agent {name!r} — registered: " + ", ".join(sorted(agents))
        ) from None


def display_name(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").title()


# --- Agent name sidecar ---
#
# Same file and format as the example server (agent_type.json), so
# sessions recorded by either are mutually readable.


def save_agent_name(manager: SessionManager, session_id: str, name: str) -> None:
    sidecar = manager.base_dir / session_id / "agent_type.json"
    sidecar.write_text(json.dumps({"agent_type": name}))


def load_agent_name(manager: SessionManager, session_id: str) -> str:
    sidecar = manager.base_dir / session_id / "agent_type.json"
    if not sidecar.exists():
        raise FileNotFoundError(f"agent_type.json not found for session {session_id}")
    return json.loads(sidecar.read_text())["agent_type"]


# --- Session lifecycle ---


async def create_session(
    agents: dict[str, Agent],
    manager: SessionManager,
    agent_name: str | None,
) -> tuple[str, Session]:
    """Create a session on the named agent and record which agent owns it."""
    name, agent = resolve_agent(agents, agent_name)
    session = await agent.create_session()
    save_agent_name(manager, session.session_id, name)
    return name, session


async def resume_session(
    agents: dict[str, Agent],
    manager: SessionManager,
    session_id: str,
) -> tuple[Agent, Session]:
    """Route a session back to its live agent and resume it.

    agent.load_session() rebuilds the system prompt fresh and validates
    that the session's model/backend/workspace still match the agent —
    a mismatch (e.g. the user changed the model in their app file)
    surfaces as SessionConfigMismatchError.
    """
    name = load_agent_name(manager, session_id)
    _, agent = resolve_agent(agents, name)
    session = await agent.load_session(session_id)
    return agent, session


def open_session_readonly(manager: SessionManager, session_id: str) -> Session:
    """Load a session for inspection only (metadata + stored messages).

    Deliberately promptless: read-only consumers serialize the stored
    conversation and never run the agent. To run the agent, use
    resume_session().
    """
    meta = manager.read_meta(session_id)
    return manager.load_session(
        session_id,
        model=meta.model,
        backend=meta.backend,
        behavior_prompt=None,
    )
