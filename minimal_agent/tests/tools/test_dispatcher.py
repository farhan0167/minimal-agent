"""Tests for `tools.dispatcher.dispatch`.

Covers every branch the dispatcher can take: unknown tool, Pydantic
validation failure, semantic validation failure, tool raising, and the
happy path. Tools are built inline — no agent loop required.
"""

from typing import ClassVar

from pydantic import BaseModel

from llm.types import Role, ToolCall
from tools import (
    BaseTool,
    ToolContext,
    ValidationErr,
    ValidationOk,
    ValidationResult,
    dispatch,
)


class EchoInput(BaseModel):
    """Echo the given text back."""

    text: str


class EchoTool(BaseTool[EchoInput, str]):
    name: ClassVar[str] = "echo"
    input_schema: ClassVar[type[BaseModel]] = EchoInput
    is_read_only: ClassVar[bool] = True

    async def invoke(self, args: EchoInput, ctx: ToolContext) -> str:
        return args.text


class BoomTool(BaseTool[EchoInput, str]):
    name: ClassVar[str] = "boom"
    input_schema: ClassVar[type[BaseModel]] = EchoInput

    async def invoke(self, args: EchoInput, ctx: ToolContext) -> str:
        raise RuntimeError("kaboom")


class RejectingTool(BaseTool[EchoInput, str]):
    name: ClassVar[str] = "rejecting"
    input_schema: ClassVar[type[BaseModel]] = EchoInput

    async def validate(self, args: EchoInput, ctx: ToolContext) -> ValidationResult:
        return ValidationErr(message="nope")

    async def invoke(self, args: EchoInput, ctx: ToolContext) -> str:
        return "unreachable"


def _call(name: str, arguments: dict) -> ToolCall:
    return ToolCall(id="call_1", name=name, arguments=arguments)


async def test_happy_path_renders_result():
    tools = {"echo": EchoTool()}
    msg = await dispatch(_call("echo", {"text": "hi"}), tools, ToolContext())
    assert msg.role == Role.TOOL
    assert msg.tool_call_id == "call_1"
    assert msg.content == "hi"


async def test_unknown_tool_returns_error_message():
    msg = await dispatch(_call("missing", {}), {}, ToolContext())
    assert msg.role == Role.TOOL
    assert "unknown tool" in msg.content
    assert "'missing'" in msg.content


async def test_pydantic_validation_failure_surfaced():
    tools = {"echo": EchoTool()}
    # Missing required `text` field.
    msg = await dispatch(_call("echo", {}), tools, ToolContext())
    assert "invalid arguments" in msg.content


async def test_semantic_validation_failure_surfaced():
    tools = {"rejecting": RejectingTool()}
    msg = await dispatch(_call("rejecting", {"text": "x"}), tools, ToolContext())
    assert "validation failed" in msg.content
    assert "nope" in msg.content


async def test_invoke_exception_becomes_error_message():
    """A raising tool must not bring down the dispatcher — the model sees
    the error and can recover."""
    tools = {"boom": BoomTool()}
    msg = await dispatch(_call("boom", {"text": "x"}), tools, ToolContext())
    assert msg.role == Role.TOOL
    assert "tool error" in msg.content
    assert "RuntimeError" in msg.content
    assert "kaboom" in msg.content


async def test_validation_ok_default_allows_invoke():
    """Default `validate` returns ValidationOk — happy path should reach invoke."""
    result = await EchoTool().validate(EchoInput(text="x"), ToolContext())
    assert isinstance(result, ValidationOk)


# -- Permission tests --------------------------------------------------------


class PermissionTool(BaseTool[EchoInput, str]):
    """A tool that always requires permission."""

    name: ClassVar[str] = "guarded"
    input_schema: ClassVar[type[BaseModel]] = EchoInput

    async def invoke(self, args: EchoInput, ctx: ToolContext) -> str:
        return args.text

    def needs_permission(self, args: EchoInput) -> bool:
        return True

    def permission_description(self, args: EchoInput) -> str:
        return f"Echo '{args.text}'"


async def test_permission_denied_blocks_invoke():
    """When the callback returns False, the tool is not executed."""

    async def deny(_name: str, _desc: str) -> bool:
        return False

    ctx = ToolContext(permission_callback=deny)
    tools = {"guarded": PermissionTool()}
    msg = await dispatch(_call("guarded", {"text": "secret"}), tools, ctx)
    assert "permission denied" in msg.content
    assert "guarded" in msg.content


async def test_permission_allowed_executes():
    """When the callback returns True, the tool runs normally."""

    async def allow(_name: str, _desc: str) -> bool:
        return True

    ctx = ToolContext(permission_callback=allow)
    tools = {"guarded": PermissionTool()}
    msg = await dispatch(_call("guarded", {"text": "hello"}), tools, ctx)
    assert msg.content == "hello"


async def test_permission_not_checked_when_no_callback():
    """When no callback is set, tools that need permission still execute."""
    ctx = ToolContext()  # no callback
    tools = {"guarded": PermissionTool()}
    msg = await dispatch(_call("guarded", {"text": "hello"}), tools, ctx)
    assert msg.content == "hello"


async def test_permission_not_checked_when_tool_doesnt_need_it():
    """Tools that return needs_permission=False skip the callback entirely."""
    called = False

    async def should_not_be_called(_name: str, _desc: str) -> bool:
        nonlocal called
        called = True
        return True

    ctx = ToolContext(permission_callback=should_not_be_called)
    tools = {"echo": EchoTool()}
    msg = await dispatch(_call("echo", {"text": "hi"}), tools, ctx)
    assert msg.content == "hi"
    assert not called


async def test_permission_callback_receives_description():
    """The callback receives the tool name and permission description."""
    received: list[tuple[str, str]] = []

    async def capture(name: str, desc: str) -> bool:
        received.append((name, desc))
        return True

    ctx = ToolContext(permission_callback=capture)
    tools = {"guarded": PermissionTool()}
    await dispatch(_call("guarded", {"text": "yo"}), tools, ctx)
    assert len(received) == 1
    assert received[0][0] == "guarded"
    assert "yo" in received[0][1]


async def test_permission_callback_error_surfaces():
    """If the callback itself raises, the error is captured gracefully."""

    async def boom(_name: str, _desc: str) -> bool:
        raise RuntimeError("prompt crashed")

    ctx = ToolContext(permission_callback=boom)
    tools = {"guarded": PermissionTool()}
    msg = await dispatch(_call("guarded", {"text": "x"}), tools, ctx)
    assert "permission error" in msg.content
    assert "prompt crashed" in msg.content
