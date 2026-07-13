"""minimal_agent — a minimal async agent framework."""

from typing import TYPE_CHECKING

from .agent import (
    Agent,
    Context,
    Scope,
    Session,
    SessionManager,
    SessionView,
    Transcript,
)
from .audit import (
    ReconstructedCall,
    RunSummary,
    RunView,
    SpawnedAgent,
    find_agent_scope,
    reconstruct_call,
    run_summaries,
    session_runs,
    single_run,
)
from .config import Settings

_SERVER_EXTRA_HINT = (
    'App requires the server extra — pip install "mini-agent-kit[server]"'
)

if TYPE_CHECKING:
    # Runtime import stays lazy (see __getattr__ below), but type checkers
    # evaluate this branch as always-true, so `from minimal_agent import App`
    # resolves for autocompletion and highlighting without pulling in the
    # server extra at runtime.
    from .server import App


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
    "RunSummary",
    "RunView",
    "Scope",
    "Session",
    "SessionManager",
    "SessionView",
    "Settings",
    "SpawnedAgent",
    "Transcript",
    "find_agent_scope",
    "reconstruct_call",
    "run_summaries",
    "session_runs",
    "single_run",
]
