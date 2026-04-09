"""Request/response Pydantic models for the API."""

from datetime import datetime

from pydantic import BaseModel, Field


# --- Requests ---


class CreateSessionRequest(BaseModel):
    workspace_root: str = Field(
        description="Absolute path to the project directory the agent works in."
    )
    model: str | None = Field(
        default=None,
        description="LLM model name. Falls back to server default.",
    )
    backend: str | None = Field(
        default=None,
        description="LLM backend (openai, openrouter, anthropic, localhost).",
    )


class ChatRequest(BaseModel):
    message: str = Field(description="The user message to send to the agent.")


# --- Responses ---


class SessionResponse(BaseModel):
    session_id: str
    workspace_root: str | None = None
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
