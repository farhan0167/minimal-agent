"""Per-call harness context passed into every tool invocation.

See [.claude/specifications/tool-system.md](../.claude/specifications/tool-system.md)
for the design rules. Rule: no field lands here speculatively. Each one
arrives with the first tool that genuinely needs it.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..agent.scope import Scope

# Signature: (tool_name, description_of_what_it_wants_to_do) → allowed?
PermissionCallback = Callable[[str, str], Awaitable[bool]]


def _null_scope() -> "Scope":
    # Deferred import: tools/ must not import from agent/ at module level
    # (agent/ imports tools/ — a top-level import here would be a cycle).
    from ..agent.scope import NullScope

    return NullScope()


@dataclass
class ToolContext:
    """Cross-cutting side-channel for tool execution.

    Fields are added as concrete tools need them. The parameter exists on
    `BaseTool.invoke` from the start so new fields can be added additively
    without changing every tool's signature.
    """

    permission_callback: Optional[PermissionCallback] = field(default=None)
    # The recording node of the agent this tool call belongs to. A tool
    # that runs its own agent opens a child under it:
    #     with ctx.scope.child(spawned_by=self.name, task=...,
    #                          tool_call_id=ctx.tool_call_id) as scope: ...
    # Defaults to a NullScope, so bare ToolContexts run unrecorded.
    scope: "Scope" = field(default_factory=_null_scope)
    # Id of the tool call being dispatched — stamped by the dispatcher so
    # tools can link child scopes to the exact call that spawned them.
    tool_call_id: Optional[str] = field(default=None)
