"""Tool-call dispatcher — turns a `ToolCall` from the model into a
tool-result `Message`, running the full pipeline.

Errors never raise out of `dispatch`: a failing tool becomes a tool-result
message so the model can observe and recover. The agent loop must not crash
because a tool threw.
"""

from typing import Any, Dict

from pydantic import ValidationError

from ..llm.types import Message, Role, ToolCall
from .base import BaseTool
from .context import ToolContext


async def dispatch(
    tool_call: ToolCall,
    tools_by_name: Dict[str, BaseTool[Any, Any]],
    ctx: ToolContext,
) -> Message:
    """Execute one tool call and return the resulting tool-role Message."""
    tool = tools_by_name.get(tool_call.name)
    if tool is None:
        return Message(
            role=Role.TOOL,
            tool_call_id=tool_call.id,
            content=f"error: unknown tool {tool_call.name!r}",
        )

    # 1. Parse + Pydantic-validate the model's JSON into the input schema.
    try:
        args = tool.input_schema.model_validate(tool_call.arguments)
    except ValidationError as e:
        return Message(
            role=Role.TOOL,
            tool_call_id=tool_call.id,
            content=f"invalid arguments: {e}",
        )

    # 2. Semantic validation (path escape, allowlists, etc.)
    validation = await tool.validate(args, ctx)
    if not validation.ok:
        return Message(
            role=Role.TOOL,
            tool_call_id=tool_call.id,
            content=f"validation failed: {validation.message}",
        )

    # 3. Permission check.
    if tool.needs_permission(args) and ctx.permission_callback is not None:
        description = tool.permission_description(args)
        try:
            allowed = await ctx.permission_callback(tool_call.name, description)
        except Exception as e:
            return Message(
                role=Role.TOOL,
                tool_call_id=tool_call.id,
                content=f"permission error: {type(e).__name__}: {e}",
            )
        if not allowed:
            return Message(
                role=Role.TOOL,
                tool_call_id=tool_call.id,
                content=f"permission denied: user rejected {tool_call.name}",
            )

    # 4. Execute.
    try:
        out = await tool.invoke(args, ctx)
    except Exception as e:
        return Message(
            role=Role.TOOL,
            tool_call_id=tool_call.id,
            content=f"tool error: {type(e).__name__}: {e}",
        )

    # 5. Serialize for the assistant.
    return Message(
        role=Role.TOOL,
        tool_call_id=tool_call.id,
        content=tool.render_result_for_assistant(out),
    )
