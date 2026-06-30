"""Chat endpoint — streams agent responses via SSE."""

import asyncio
import base64
import io
import json
import traceback
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from minimal_agent.agent import INTERRUPTED_RESPONSE_MARKER, Session
from minimal_agent.llm.types import (
    ImagePart,
    ImageUrl,
    Message,
    Role,
    StreamChunk,
    TextPart,
)
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


def _last_role_is_user(session: Session) -> bool:
    """True if the session's last stored message is an unanswered user turn.

    Guards the interrupt commit: if agent.run() already committed this turn's
    assistant message before the disconnect (e.g. interrupted during tool
    dispatch), the last role is assistant/tool and we must not append a
    second, spurious marker.
    """
    messages = session.context.store.messages
    return bool(messages) and messages[-1].role == Role.USER


def _commit_interrupted(session: Session, pending_text: str) -> None:
    """Persist an assistant message for a turn cut off mid-stream.

    Records whatever text streamed before the disconnect, tagged with the
    interrupted marker, so the conversation stays role-alternating and the
    model sees on its next turn that the previous reply never completed. When
    nothing streamed yet, the marker alone is committed.
    """
    if pending_text:
        content = f"{pending_text}\n\n{INTERRUPTED_RESPONSE_MARKER}"
    else:
        content = INTERRUPTED_RESPONSE_MARKER
    session.context.add(Message(role=Role.ASSISTANT, content=content))


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

    # Tracks assistant text streamed for the *current* turn but not yet
    # committed to the session by agent.run(). agent.run() only commits the
    # assistant Message after the full turn streams; if the client disconnects
    # mid-stream the generator is cancelled before that, leaving the user
    # message unanswered. We commit a partial assistant message on the way out
    # so the conversation stays role-alternating and the model sees that its
    # previous reply was interrupted.
    pending_text = ""
    try:
        async for item in agent.run(
            session.context,
            stream=True,
            on_usage=on_usage,
            permission_callback=auto_approve,
        ):
            # Token deltas arrive first; the committed assistant Message
            # follows and carries the full text (clients should treat it as
            # authoritative and replace, not append).
            if isinstance(item, StreamChunk):
                if item.text:
                    pending_text += item.text
                    yield {"event": "delta", "data": json.dumps({"text": item.text})}
            elif item.role == Role.ASSISTANT:
                # This turn's assistant message is now committed by agent.run();
                # reset the pending buffer so we don't double-commit it.
                pending_text = ""
                yield {"event": "assistant", "data": _serialize_message(item)}
            elif item.role == Role.TOOL:
                yield {"event": "tool_result", "data": _serialize_message(item)}
    except (asyncio.CancelledError, GeneratorExit):
        # Stream was torn down before the turn finished. On a client
        # disconnect sse-starlette calls aclose() on this generator, which
        # raises GeneratorExit at the suspended yield; a server shutdown / task
        # cancel raises CancelledError. Either way agent.run() never committed
        # this turn's assistant message. Persist whatever streamed (plus an
        # interrupted marker) so history stays role-alternating and the
        # interruption is on the record for the next turn, then re-raise.
        #
        # context.add() persists synchronously (no await), which is required
        # here: awaiting during GeneratorExit handling is illegal.
        if pending_text or _last_role_is_user(session):
            _commit_interrupted(session, pending_text)
        raise
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
