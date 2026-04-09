"""Per-call harness context passed into every tool invocation.

See [.claude/specifications/tool-system.md](../.claude/specifications/tool-system.md)
for the design rules. Rule: no field lands here speculatively. Each one
arrives with the first tool that genuinely needs it.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Optional

# Signature: (tool_name, description_of_what_it_wants_to_do) → allowed?
PermissionCallback = Callable[[str, str], Awaitable[bool]]


@dataclass
class ToolContext:
    """Cross-cutting side-channel for tool execution.

    Fields are added as concrete tools need them. The parameter exists on
    `BaseTool.invoke` from the start so new fields can be added additively
    without changing every tool's signature.
    """

    permission_callback: Optional[PermissionCallback] = field(default=None)
