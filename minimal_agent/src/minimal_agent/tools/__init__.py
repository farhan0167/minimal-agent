"""Tool authoring framework and dispatcher.

Authors write `from tools import BaseTool, ToolContext` and implement a
subclass. Concrete tools live under `tools.builtin.<tool_name>`.
"""

from .base import BaseTool, InputModel, Out
from .context import ToolContext
from .dispatcher import dispatch
from .results import (
    PermissionAllow,
    PermissionDeny,
    PermissionResult,
    ValidationErr,
    ValidationOk,
    ValidationResult,
)

__all__ = [
    "BaseTool",
    "InputModel",
    "Out",
    "ToolContext",
    "ValidationOk",
    "ValidationErr",
    "ValidationResult",
    "PermissionAllow",
    "PermissionDeny",
    "PermissionResult",
    "dispatch",
]
