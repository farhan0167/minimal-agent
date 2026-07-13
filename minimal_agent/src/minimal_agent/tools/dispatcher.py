"""Tool-call dispatcher — turns a `ToolCall` from the model into a
tool-result `Message`, running the full pipeline.

Errors never raise out of `dispatch`: a failing tool becomes a tool-result
message so the model can observe and recover. The agent loop must not crash
because a tool threw.

Every dispatch is bracketed by tool.start/tool.end events on the context's
scope — how permission denials, validation failures, and tool exceptions
enter the timeline, with durations. tool.end also carries the ids of any
child scopes the tool spawned, as a second join path to their records.
"""

import time
from dataclasses import replace
from typing import Any, Dict, Tuple

from pydantic import ValidationError

from ..events import ToolEnd, ToolStart, ToolStatus
from ..llm.types import ContentPart, Message, Role, ToolCall
from .base import BaseTool
from .context import ToolContext


async def dispatch(
    tool_call: ToolCall,
    tools_by_name: Dict[str, BaseTool[Any, Any]],
    ctx: ToolContext,
) -> Tuple[Message, list[ContentPart]]:
    """Execute one tool call → (tool-role Message, relocatable content parts).

    The parts list is non-empty only when a multimodal tool produced content
    (e.g. an image) the API forbids on a `tool` message. The agent loop
    relocates those parts onto a trailing user message after the tool batch is
    answered. For text-only tools — and every error path — it is empty.
    """
    # Per-call copy: the caller's ToolContext is shared across a turn's
    # tool calls; the id must not leak from one call into the next.
    ctx = replace(ctx, tool_call_id=tool_call.id)
    ctx.session.events.emit(ToolStart(tool_call_id=tool_call.id, name=tool_call.name))
    t0 = time.monotonic()
    status, msg, parts = await _dispatch_inner(tool_call, tools_by_name, ctx)
    # children_of() is recording plumbing, deliberately absent from the env's
    # curated surface — the dispatcher is framework code and reaches the
    # scope directly rather than widening what tools can see.
    children = tuple(ctx.session._scope.children_of(tool_call.id))
    ctx.session.events.emit(
        ToolEnd(
            tool_call_id=tool_call.id,
            name=tool_call.name,
            status=status,
            duration_ms=int((time.monotonic() - t0) * 1000),
            children=children,
        )
    )
    return msg, parts


async def _dispatch_inner(
    tool_call: ToolCall,
    tools_by_name: Dict[str, BaseTool[Any, Any]],
    ctx: ToolContext,
) -> Tuple[ToolStatus, Message, list[ContentPart]]:
    """The pipeline. Each exit maps to exactly one ToolStatus.

    Only the success path can carry content parts; every error path returns an
    empty parts list.
    """
    tool = tools_by_name.get(tool_call.name)
    if tool is None:
        return (
            ToolStatus.UNKNOWN_TOOL,
            Message(
                role=Role.TOOL,
                tool_call_id=tool_call.id,
                content=f"error: unknown tool {tool_call.name!r}",
            ),
            [],
        )

    # 1. Parse + Pydantic-validate the model's JSON into the input schema.
    try:
        args = tool.input_schema.model_validate(tool_call.arguments)
    except ValidationError as e:
        return (
            ToolStatus.INVALID_ARGS,
            Message(
                role=Role.TOOL,
                tool_call_id=tool_call.id,
                content=f"invalid arguments: {e}",
            ),
            [],
        )

    # 2. Semantic validation (path escape, allowlists, etc.)
    validation = await tool.validate(args, ctx)
    if not validation.ok:
        return (
            ToolStatus.VALIDATION_FAILED,
            Message(
                role=Role.TOOL,
                tool_call_id=tool_call.id,
                content=f"validation failed: {validation.message}",
            ),
            [],
        )

    # 3. Permission check.
    if tool.needs_permission(args) and ctx.permission_callback is not None:
        description = tool.permission_description(args)
        try:
            allowed = await ctx.permission_callback(tool_call.name, description)
        except Exception as e:
            return (
                ToolStatus.PERMISSION_ERROR,
                Message(
                    role=Role.TOOL,
                    tool_call_id=tool_call.id,
                    content=f"permission error: {type(e).__name__}: {e}",
                ),
                [],
            )
        if not allowed:
            return (
                ToolStatus.DENIED,
                Message(
                    role=Role.TOOL,
                    tool_call_id=tool_call.id,
                    content=f"permission denied: user rejected {tool_call.name}",
                ),
                [],
            )

    # 4. Execute.
    try:
        out = await tool.invoke(args, ctx)
    except Exception as e:
        return (
            ToolStatus.ERROR,
            Message(
                role=Role.TOOL,
                tool_call_id=tool_call.id,
                content=f"tool error: {type(e).__name__}: {e}",
            ),
            [],
        )

    # 5. Serialize for the assistant. Text goes on the tool message; any
    # non-text parts (images) are handed back for the loop to relocate.
    return (
        ToolStatus.OK,
        Message(
            role=Role.TOOL,
            tool_call_id=tool_call.id,
            content=tool.render_result_for_assistant(out),
        ),
        tool.render_parts_for_assistant(out),
    )
