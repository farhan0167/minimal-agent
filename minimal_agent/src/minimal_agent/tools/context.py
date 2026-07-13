"""Per-call harness context passed into every tool invocation.

See [.claude/specifications/tool-system.md](../.claude/specifications/tool-system.md)
for the design rules. Rule: no field lands here speculatively. Each one
arrives with the first tool that genuinely needs it.

The rule the two carriers encode:
    session-scoped capability → a SessionView facet (ctx.session)
    call-scoped payload       → a ToolContext field
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..agent.view import SessionView

# Signature: (tool_name, description_of_what_it_wants_to_do) → allowed?
PermissionCallback = Callable[[str, str], Awaitable[bool]]


def _bare_session() -> "SessionView":
    # Deferred import: tools/ must not import from agent/ at module level
    # (agent/ imports tools/ — a top-level import here would be a cycle).
    from ..agent.scope import NullScope
    from ..agent.view import SessionView

    return SessionView(scope=NullScope())


@dataclass
class ToolContext:
    """Cross-cutting side-channel for tool execution.

    Fields are added as concrete tools need them. The parameter exists on
    `BaseTool.invoke` from the start so new fields can be added additively
    without changing every tool's signature.
    """

    permission_callback: Optional[PermissionCallback] = field(default=None)
    # The session this tool call is running in, as seen from inside: the
    # workspace root, the conversation so far (ctx.session.transcript), a
    # per-session directory to remember things in (ctx.session.state_dir),
    # the event seam, and spawn() for tools that run their own agent:
    #     with ctx.session.spawn(spawned_by=self.name, task=...,
    #                            tool_call_id=ctx.tool_call_id) as scope: ...
    # Everything session-specific arrives here, per call — never through a
    # tool's constructor, which is agent-level state shared across every
    # session that agent serves. Defaults to a bare view, so bare
    # ToolContexts run unrecorded with tempdir-backed state.
    session: "SessionView" = field(default_factory=_bare_session)
    # Id of the tool call being dispatched — stamped by the dispatcher so
    # tools can link child scopes to the exact call that spawned them.
    tool_call_id: Optional[str] = field(default=None)
