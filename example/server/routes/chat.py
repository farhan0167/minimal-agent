"""Chat endpoint — streams agent responses via SSE."""

import base64
import io
import json
import traceback
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from minimal_agent.llm.types import ImagePart, ImageUrl, Message, Role, TextPart
from pdf2image import convert_from_bytes
from sse_starlette.sse import EventSourceResponse

from app import build_agent, load_agent_type, load_session, validate_workspace
from schemas import AttachmentContent, ChatRequest

router = APIRouter(prefix="/sessions", tags=["chat"])


def _pdf_to_image_parts(data_uri: str) -> list[ImagePart]:
    """Convert a base64 PDF data URI into ImageParts (one per page)."""
    # Strip the data URI prefix to get raw base64
    header, b64data = data_uri.split(",", 1)
    pdf_bytes = base64.b64decode(b64data)

    images = convert_from_bytes(pdf_bytes)
    parts: list[ImagePart] = []
    for page_img in images:
        buf = io.BytesIO()
        page_img.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode()
        parts.append(
            ImagePart(image_url=ImageUrl(url=f"data:image/png;base64,{img_b64}"))
        )
    return parts


def _attachment_to_image_parts(att: AttachmentContent) -> list[ImagePart]:
    """Convert an attachment to ImagePart(s), handling PDF conversion."""
    if att.mime_type == "application/pdf":
        return _pdf_to_image_parts(att.data)
    # Regular image — pass through as-is.
    return [ImagePart(image_url=ImageUrl(url=att.data, detail=att.detail))]


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

    agent_type = load_agent_type(session_id)
    agent = build_agent(agent_type, workspace, model=session._meta.model, backend=session._meta.backend)

    # Build user message — multimodal when attachments are present.
    if req.attachments:
        content: list[TextPart | ImagePart] = [TextPart(text=req.message)]
        for att in req.attachments:
            content.extend(_attachment_to_image_parts(att))
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
