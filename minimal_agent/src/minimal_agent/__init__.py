"""minimal_agent — a minimal async agent framework."""

from .agent import Agent, Context, Scope, Session, SessionManager
from .audit import (
    ReconstructedCall,
    RunView,
    ScopeView,
    SpawnedAgent,
    reconstruct_call,
    session_runs,
    session_tree,
)
from .config import Settings

_SERVER_EXTRA_HINT = (
    'App requires the server extra — pip install "minimal-agent[server]"'
)


def __getattr__(name: str):
    # Lazy: the server stack (fastapi, uvicorn, sse-starlette) is an
    # optional extra, so `from minimal_agent import App` must not force
    # the import cost (or the dependency) on library-only users.
    if name == "App":
        try:
            from .server import App
        except ImportError as e:
            raise ImportError(_SERVER_EXTRA_HINT) from e
        return App
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Agent",
    "App",
    "Context",
    "ReconstructedCall",
    "RunView",
    "Scope",
    "ScopeView",
    "Session",
    "SessionManager",
    "Settings",
    "SpawnedAgent",
    "reconstruct_call",
    "session_runs",
    "session_tree",
]
