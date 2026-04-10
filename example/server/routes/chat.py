"""Chat endpoint — streams agent responses via SSE."""

import json
import traceback
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app import build_agent, load_session, validate_workspace
from minimal_agent.llm.types import ImagePart, ImageUrl, Message, Role, TextPart
from schemas import ChatRequest

router = APIRouter(prefix="/sessions", tags=["chat"])


def _serialize_message(msg: Message) -> str:
    """Serialize a Message to JSON for SSE."""
    if isinstance(msg.content, list):
        content = [part.model_dump(exclude_none=True) for part in msg.content]
    else:
        content = msg.content
    data: dict = {"role": msg.role.value, "content": content}
    if msg.tool_calls:
        data["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
    if msg.tool_call_id:
        data["tool_call_id"] = msg.tool_call_id
    return json.dumps(data)


async def _stream_agent(
    session_id: str,
    req: ChatRequest,
) -> AsyncGenerator[dict, None]:
    """Run the agent loop and yield SSE events."""
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        yield {"event": "error", "data": json.dumps({"detail": "Session not found"})}
        return

    workspace_root = session._meta.workspace_root
    if not workspace_root:
        yield {
            "event": "error",
            "data": json.dumps({"detail": "Session has no workspace_root"}),
        }
        return

    try:
        workspace = validate_workspace(workspace_root)
    except ValueError as e:
        yield {"event": "error", "data": json.dumps({"detail": str(e)})}
        return

    agent = build_agent(workspace, model=session._meta.model, backend=session._meta.backend)

    # Build user message — multimodal when images are attached.
    if req.images:
        content: list[TextPart | ImagePart] = [TextPart(text=req.message)]
        for img in req.images:
            content.append(ImagePart(image_url=ImageUrl(url=img.data, detail=img.detail)))
        session.context.add(Message(role=Role.USER, content=content))
    else:
        session.context.add(Message(role=Role.USER, content=req.message))

    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def on_usage(usage):
        usage_total["prompt_tokens"] += usage.prompt_tokens
        usage_total["completion_tokens"] += usage.completion_tokens
        usage_total["total_tokens"] += usage.total_tokens
        session.update_usage(usage)

    async def auto_approve(tool_name: str, description: str) -> bool:
        return True

    try:
        async for msg in agent.run(
            session.context,
            on_usage=on_usage,
            permission_callback=auto_approve,
        ):
            if msg.role == Role.ASSISTANT:
                yield {"event": "assistant", "data": _serialize_message(msg)}
            elif msg.role == Role.TOOL:
                yield {"event": "tool_result", "data": _serialize_message(msg)}
    except Exception as e:
        yield {
            "event": "error",
            "data": json.dumps(
                {"detail": str(e), "traceback": traceback.format_exc()}
            ),
        }

    yield {"event": "done", "data": json.dumps({"usage": usage_total})}


@router.post("/{session_id}/chat")
async def chat_route(session_id: str, req: ChatRequest):
    # Validate session exists before starting stream.
    try:
        load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")

    return EventSourceResponse(_stream_agent(session_id, req))


@router.get("/{session_id}/messages")
async def messages_route(session_id: str):
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = session.context.get_messages()
    return {
        "messages": [
            {
                "role": msg.role.value,
                "content": (
                    [part.model_dump(exclude_none=True) for part in msg.content]
                    if isinstance(msg.content, list)
                    else msg.content
                ),
                "tool_call_id": msg.tool_call_id,
                "tool_calls": (
                    [tc.model_dump() for tc in msg.tool_calls]
                    if msg.tool_calls
                    else None
                ),
            }
            for msg in messages
        ]
    }
