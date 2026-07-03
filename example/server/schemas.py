"""Request/response Pydantic models for the API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# --- Requests ---


class CreateSessionRequest(BaseModel):
    workspace_root: str = Field(
        description="Absolute path to the project directory the agent works in."
    )
    agent_type: str = Field(
        description="Agent type to use for this session (e.g. 'swe', 'research')."
    )
    model: str | None = Field(
        default=None,
        description="LLM model name. Falls back to server default.",
    )
    backend: str | None = Field(
        default=None,
        description="LLM backend (openai, openrouter, anthropic, localhost).",
    )


class AttachmentContent(BaseModel):
    """A base64-encoded file attachment (image or PDF)."""

    data: str = Field(description="Base64 data URI (e.g. 'data:image/png;base64,...').")
    mime_type: str = Field(
        description="MIME type of the attachment (e.g. 'image/png', 'application/pdf')."
    )
    detail: Literal["auto", "low", "high"] | None = Field(
        default=None,
        description="Vision detail level hint (applicable to images).",
    )


class ChatRequest(BaseModel):
    message: str = Field(description="The user message to send to the agent.")
    attachments: list[AttachmentContent] | None = Field(
        default=None,
        description="Optional file attachments (images, PDFs) as base64 data URIs.",
    )


# --- Responses ---


class SessionResponse(BaseModel):
    session_id: str
    workspace_root: str | None = None
    agent_type: str
    model: str
    backend: str
    created_at: datetime
    updated_at: datetime
    usage: dict | None = None


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]


class MessageResponse(BaseModel):
    role: str
    content: str | list | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None


class MessageHistoryResponse(BaseModel):
    messages: list[MessageResponse]


class ToolInfo(BaseModel):
    name: str


class ToolListResponse(BaseModel):
    tools: list[ToolInfo]


# --- Observability (events.jsonl / calls.jsonl / reconstruction) ---


class EventListResponse(BaseModel):
    """The session timeline: raw envelopes from events.jsonl, in order."""

    events: list[dict]


class CallRecordListResponse(BaseModel):
    """Raw audit records from calls.jsonl, one per LLM call."""

    calls: list[dict]


class ReconstructedCallResponse(BaseModel):
    """One LLM call's exact input, rebuilt from the session directory."""

    call_id: str
    run_id: str | None = None
    ts: str
    model: str | None = None
    backend: str | None = None
    verified: bool = Field(
        description=(
            "Whether the rebuilt messages hash to the recorded value. False "
            "means unverifiable (e.g. serialization drift), not tampered."
        )
    )
    recorded_sha256: str
    computed_sha256: str
    tools: list[dict] | None = Field(
        default=None, description="Tool schemas the model was offered."
    )
    messages: list[MessageResponse] = Field(
        description="Exactly what the model saw on this call, in order."
    )


class ToolExecutionInfo(BaseModel):
    """One tool dispatch within a call."""

    tool_call_id: str
    name: str
    status: str | None = Field(
        default=None, description="Null if the dispatch never returned."
    )
    duration_ms: int | None = None


class CallViewResponse(BaseModel):
    """One LLM call, fully expanded: input, response, and tool activity."""

    call_id: str
    ts: str
    input: ReconstructedCallResponse
    response: MessageResponse | None = Field(
        default=None,
        description=(
            "The model's reply to this call. Null if the call never "
            "completed (crash/disconnect before the reply was stored)."
        ),
    )
    latency_ms: int | None = None
    usage: dict | None = None
    tool_executions: list[ToolExecutionInfo]


class RunViewResponse(BaseModel):
    """One agent run and every LLM call it made."""

    run_id: str
    started_at: str | None = None
    model: str | None = None
    backend: str | None = None
    status: str | None = Field(
        default=None,
        description=(
            "completed | max_turns | abandoned | error; null if the run "
            "never finalized or was recorded without a run frame."
        ),
    )
    duration_ms: int | None = None
    calls: list[CallViewResponse]


class RunListResponse(BaseModel):
    """The holistic view: every model input and output, by run and call."""

    runs: list[RunViewResponse]
