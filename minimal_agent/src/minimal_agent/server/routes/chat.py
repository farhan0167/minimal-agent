"""Chat endpoint — streams agent responses via SSE."""

import asyncio
import base64
import io
import json
import traceback
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from ...agent import (
    INTERRUPTED_RESPONSE_MARKER,
    Agent,
    Session,
    SessionConfigMismatchError,
    SessionManager,
)
from ...llm.types import (
    ImagePart,
    ImageUrl,
    Message,
    Role,
    StreamChunk,
    TextPart,
)
from ..deps import get_agents, get_manager
from ..schemas import AttachmentContent, ChatRequest
from ..service import UnknownAgentError, open_session_readonly, resume_session

# PDF attachments need pdf2image (and system poppler underneath) — too
# heavy to require of every server user, so support is feature-detected.
try:
    from pdf2image import convert_from_bytes

    _PDF_SUPPORT = True
except ImportError:
    _PDF_SUPPORT = False

_PDF_UNAVAILABLE = (
    "PDF attachments require the pdf2image package and poppler "
    '(pip install "mini-agent-kit[pdf]"; apt/brew install poppler)'
)

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
    if msg.reasoning:
        data["reasoning"] = msg.reasoning
    return json.dumps(data)


async def _stream_agent(
    agents: dict[str, Agent],
    manager: SessionManager,
    session_id: str,
    req: ChatRequest,
) -> AsyncGenerator[dict, None]:
    """Run the agent loop and yield SSE events."""
    try:
        agent, session = await resume_session(agents, manager, session_id)
    except FileNotFoundError:
        yield {"event": "error", "data": json.dumps({"detail": "Session not found"})}
        return
    except (UnknownAgentError, SessionConfigMismatchError, ValueError) as e:
        # Session exists but can't run against the registered agents —
        # e.g. its agent name isn't registered anymore, or the agent's
        # model/backend/workspace changed since the session was created.
        yield {"event": "error", "data": json.dumps({"detail": str(e)})}
        return

    has_pdf = any(att.mime_type == "application/pdf" for att in req.attachments or [])
    if has_pdf and not _PDF_SUPPORT:
        yield {"event": "error", "data": json.dumps({"detail": _PDF_UNAVAILABLE})}
        return

    # Build user message — multimodal when attachments are present.
    if req.attachments:
        content: list[TextPart | ImagePart] = [TextPart(text=req.message)]
        for att in req.attachments:
            content.extend(_attachment_to_image_parts(att))
        session.context.add(Message(role=Role.USER, content=content))
    else:
        session.context.add(Message(role=Role.USER, content=req.message))

    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # Display-only tally for the SSE "done" event. Session accounting is
    # automatic — the session subscribes to its scope's usage totals.
    def on_usage(usage):
        usage_total["prompt_tokens"] += usage.prompt_tokens
        usage_total["completion_tokens"] += usage.completion_tokens
        usage_total["total_tokens"] += usage.total_tokens

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
                # Reasoning arrives before the answer text; stream it on its own
                # channel so clients keep it separate from the committed content.
                if item.reasoning:
                    yield {
                        "event": "reasoning",
                        "data": json.dumps({"text": item.reasoning}),
                    }
                if item.text:
                    pending_text += item.text
                    yield {"event": "delta", "data": json.dumps({"text": item.text})}
                # Tool-call argument fragments, forwarded as-is (keyed by
                # index; arguments are incremental JSON string chunks).
                # Clients accumulate them to preview in-flight calls; the
                # committed assistant message that follows is authoritative.
                if item.tool_calls:
                    yield {
                        "event": "tool_call_delta",
                        "data": json.dumps(
                            {
                                "tool_calls": [
                                    tcd.model_dump(exclude_none=True)
                                    for tcd in item.tool_calls
                                ]
                            }
                        ),
                    }
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
            "data": json.dumps({"detail": str(e), "traceback": traceback.format_exc()}),
        }

    yield {"event": "done", "data": json.dumps({"usage": usage_total})}


@router.post("/{session_id}/chat")
async def chat_route(
    session_id: str,
    req: ChatRequest,
    agents: dict[str, Agent] = Depends(get_agents),
    manager: SessionManager = Depends(get_manager),
):
    # Validate session exists before starting stream.
    try:
        manager.read_meta(session_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Session not found") from e

    return EventSourceResponse(_stream_agent(agents, manager, session_id, req))


@router.get("/{session_id}/messages")
async def messages_route(
    session_id: str,
    manager: SessionManager = Depends(get_manager),
):
    try:
        session = open_session_readonly(manager, session_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Session not found") from e

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
                "reasoning": msg.reasoning,
            }
            for msg in messages
        ]
    }
