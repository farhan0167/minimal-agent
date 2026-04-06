"""The `BaseTool` ABC — the interface all agent tools implement.

Tools are stateful instances constructed once at agent startup. The schema
the model sees is produced in exactly one place via `as_llm_tool`, which
delegates to `LLMTool.from_model` (and in turn the OpenAI SDK's
`pydantic_function_tool`). See
[.claude/specifications/tool-system.md](../.claude/specifications/tool-system.md).
"""

from abc import ABC, abstractmethod
from typing import ClassVar, Generic, TypeVar

from pydantic import BaseModel

from llm.types import LLMTool

from .context import ToolContext
from .results import ValidationOk, ValidationResult

InputModel = TypeVar("InputModel", bound=BaseModel)
Out = TypeVar("Out")


class BaseTool(Generic[InputModel, Out], ABC):
    """Base class for all agent tools.

    Subclasses declare the input schema, implement `invoke`, and optionally
    override hooks for permissions, validation, rendering, and read-only
    gating. A tool is instantiated once at agent startup — dependencies
    (HTTP clients, DB connections, workspace roots) are injected via
    `__init__` and live on `self`.
    """

    # Required class-level metadata — set by subclasses.
    name: ClassVar[str]
    input_schema: ClassVar[type[BaseModel]]

    # --- Required: execution ------------------------------------------------

    @abstractmethod
    async def invoke(self, args: InputModel, ctx: ToolContext) -> Out:
        """Run the tool with validated arguments.

        The dispatcher has already parsed the model's JSON into `args` and
        run semantic validation. This method should focus on the actual
        work; the dispatcher handles error surfacing and result rendering.
        """

    # --- Optional hooks (override when needed) ------------------------------

    is_read_only: ClassVar[bool] = False
    """Tools that only read state (no filesystem/network writes, no subprocess
    side-effects) set this True so the harness can gate destructive tools in
    safe/dry-run modes."""

    async def validate(self, args: InputModel, ctx: ToolContext) -> ValidationResult:
        """Semantic validation beyond what Pydantic expresses.

        Called by the dispatcher before `invoke`. Override for preconditions
        like "path must be inside workspace root" or "URL must be on the
        allowlist". Default: always valid.
        """
        return ValidationOk()

    def needs_permission(self, args: InputModel) -> bool:
        """Whether this specific invocation requires user confirmation.

        Default: False. Tools with side effects should override.
        """
        return False

    def render_result_for_assistant(self, out: Out) -> str:
        """Serialize the result into the string that goes back to the model
        as a tool-result message. Default: `str(out)`.
        """
        return str(out)

    # --- Wire-format projection ---------------------------------------------

    @classmethod
    def as_llm_tool(cls) -> LLMTool:
        """Produce the neutral LLMTool dataclass the LLM facade consumes.

        Delegates to `LLMTool.from_model`, which delegates to the OpenAI
        SDK's `pydantic_function_tool` — the strict JSON Schema lives in
        exactly one place.
        """
        return LLMTool.from_model(cls.input_schema, name=cls.name)
