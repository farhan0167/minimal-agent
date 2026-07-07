"""Request/response Pydantic models for the API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# --- Requests ---


class CreateSessionRequest(BaseModel):
    agent: str | None = Field(
        default=None,
        description=(
            "Registered agent name to bind the session to. Optional when "
            "exactly one agent is registered."
        ),
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


class AgentInfo(BaseModel):
    """One registered agent, as shown to clients."""

    name: str
    display_name: str
    workspace_root: str | None = None
    model: str
    backend: str
    tools: list[str]


class ConfigResponse(BaseModel):
    """Server facts the UI needs before creating a session."""

    version: str
    agents: list[AgentInfo]
    default_agent: str | None = Field(
        default=None,
        description="Set when exactly one agent is registered.",
    )


class SessionResponse(BaseModel):
    session_id: str
    workspace_root: str | None = None
    agent: str | None = Field(
        default=None,
        description="Registered agent name; null if the sidecar is missing "
        "(e.g. a session recorded by another consumer of the store).",
    )
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
    children: list[str] = Field(
        default_factory=list,
        description="Agent ids of child scopes this tool call spawned.",
    )


class SpawnedAgentInfo(BaseModel):
    """One nested agent spawned during a call. Its full record lives
    under agents/<agent_id>/ in the session directory."""

    agent_id: str
    spawned_by: str
    task: str
    tool_call_id: str | None = None
    status: str | None = Field(
        default=None,
        description="completed | error | abandoned; null if never closed.",
    )
    duration_ms: int | None = None
    usage: dict | None = None


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
    spawned_agents: list[SpawnedAgentInfo] = Field(default_factory=list)


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


class ScopeViewResponse(BaseModel):
    """One node of the session's recording tree: the session root
    (agent=null) or a nested agent, each with the same runs view."""

    agent: dict | None = Field(
        default=None,
        description="agent.json of a nested agent; null at the session root.",
    )
    runs: list[RunViewResponse]
    children: list["ScopeViewResponse"] = Field(default_factory=list)
