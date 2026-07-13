"""minimal_agent — a minimal async agent framework.

The names exported here are the curated common case: everything you need to
build, run, and serve an agent, plus the two extension points you need to
write a tool (`BaseTool`, `ToolContext`). The submodules hold the full
surface — `minimal_agent.llm` (message parts, reasoning, streaming),
`minimal_agent.audit` (session introspection), `minimal_agent.tools.builtin`
(the tool suite), `minimal_agent.context_sources`.
"""

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
from .config import Backend, Settings, settings
from .llm import LLM, Message, Role
from .tools import BaseTool, ToolContext

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
    #
    # `LLM` needs no such treatment: openai is a hard dependency, always
    # installed, so eager import costs nothing and keeps it statically
    # resolvable for the library's most-used symbol.
    if name == "App":
        try:
            from .server import App
        except ImportError as e:
            raise ImportError(_SERVER_EXTRA_HINT) from e
        return App
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "LLM",
    "Agent",
    "App",
    "Backend",
    "BaseTool",
    "Context",
    "Message",
    "ReconstructedCall",
    "Role",
    "RunSummary",
    "RunView",
    "Scope",
    "Session",
    "SessionManager",
    "SessionView",
    "Settings",
    "SpawnedAgent",
    "ToolContext",
    "Transcript",
    "find_agent_scope",
    "reconstruct_call",
    "run_summaries",
    "session_runs",
    "settings",
    "single_run",
]
