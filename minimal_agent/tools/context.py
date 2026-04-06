"""Per-call harness context passed into every tool invocation.

See [.claude/specifications/tool-system.md](../.claude/specifications/tool-system.md)
for the design rules. Rule: no field lands here speculatively. Each one
arrives with the first tool that genuinely needs it.
"""

from dataclasses import dataclass


@dataclass
class ToolContext:
    """Cross-cutting side-channel for tool execution.

    Intentionally empty on day one. The *parameter* exists on `BaseTool.invoke`
    from the start so new fields (cancel tokens, workspace roots, permission
    callbacks, loggers) can be added additively without changing every tool's
    signature.
    """

    pass
