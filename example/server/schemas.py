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

    data: str = Field(
        description="Base64 data URI (e.g. 'data:image/png;base64,...')."
    )
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
