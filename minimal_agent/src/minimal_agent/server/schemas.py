"""Request/response Pydantic models for the API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..llm.types import ReasoningEffort

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
    reasoning: bool = Field(
        default=True,
        description="Whether to request a reasoning/thinking trace for this "
        "turn. Ignored when the agent has no reasoning config.",
    )
    effort: ReasoningEffort | None = Field(
        default=None,
        description="Reasoning effort level for this turn "
        "(none|minimal|low|medium|high|xhigh). Ignored when reasoning=false.",
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
    reasoning: str | None = Field(
        default=None,
        description=(
            "The model's reasoning/thinking trace for this message. Null when "
            "the model produced none, or the agent has no reasoning config."
        ),
    )
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


# Mirrors ReconstructedCall.unverified_reason (audit.py), which is the source
# of truth — both call-shaped schemas below carry it, so anything the library
# knows about a call's verifiability, the API says. If _rebuild() grows a third
# producer of the reason, name it here too.
UNVERIFIED_REASON_DESC = (
    "Why this call could not be verified, when it could not. When set, "
    "`messages` is INCOMPLETE — it holds only what the recipe could truthfully "
    "recover (typically the system prompt) and must not be read as the full "
    "model input. Set when the run record is missing (the run never completed, "
    "so the system prompt is unrecoverable), or when the call predates record "
    "v3 and its projection rewrote messages whose bytes were never persisted. "
    "None means the recipe ran fully and `verified` reflects the hash "
    "comparison alone."
)


class ReconstructedCallResponse(BaseModel):
    """One LLM call's exact input, rebuilt from the session directory.

    Self-describing: carries the run-level fingerprint (model, backend, tools)
    inline because the standalone GET /calls/{call_id} endpoint has no run
    wrapper. When nested under a run (GET /runs, /runs/{run_id}), those
    run-level facts live on the run object instead — see CallInputResponse.
    """

    call_id: str
    run_id: str | None = None
    ts: str
    model: str | None = None
    backend: str | None = None
    verified: bool = Field(
        description=(
            "Whether the rebuilt messages hash to the recorded value. False "
            "means unverifiable, not tampered — see unverified_reason."
        )
    )
    unverified_reason: str | None = Field(
        default=None,
        description=UNVERIFIED_REASON_DESC,
    )
    recorded_sha256: str
    computed_sha256: str
    tools: list[dict] | None = Field(
        default=None, description="Tool schemas the model was offered."
    )
    messages: list[MessageResponse] = Field(
        description="Exactly what the model saw on this call, in order."
    )


class CallInputResponse(BaseModel):
    """One call's input as nested under a run — per-call facts only.

    The run-level fingerprint (model, backend, tools, system prompt) lives on
    the enclosing RunViewResponse, not repeated here. `messages` stays
    byte-exact (system prompt included as message[0]) so per-call verification
    and the Phoenix `llm.input_messages` mapping stay whole.
    """

    call_id: str
    run_id: str | None = None
    ts: str
    verified: bool = Field(
        description=(
            "Whether the rebuilt messages hash to the recorded value. False "
            "means unverifiable, not tampered — see unverified_reason."
        )
    )
    unverified_reason: str | None = Field(
        default=None,
        description=UNVERIFIED_REASON_DESC,
    )
    recorded_sha256: str
    computed_sha256: str
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
    """One LLM call, fully expanded: input, response, and tool activity.

    Run-level facts (model, backend, tools, system prompt) are NOT here —
    they live on the enclosing run. `input` carries only per-call detail.
    """

    call_id: str
    ts: str
    input: CallInputResponse
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
    """One agent run and every LLM call it made.

    Owns the run-level fingerprint — model, backend, tool schemas, and the
    stable system prompt — recorded once per run and shared by all its calls.
    """

    run_id: str
    started_at: str | None = None
    model: str | None = None
    backend: str | None = None
    tools: list[dict] | None = Field(
        default=None,
        description="Tool schemas the agent offered for this run.",
    )
    system_prompt: str | None = Field(
        default=None,
        description="The stable system prompt the model saw across this run.",
    )
    status: str | None = Field(
        default=None,
        description=(
            "completed | max_turns | abandoned | error; null if the run "
            "never finalized or was recorded without a run frame."
        ),
    )
    duration_ms: int | None = None
    calls: list[CallViewResponse]


class RunSummaryResponse(BaseModel):
    """A run's identity and outcome, without its calls — one row of the
    /runs index. Drill into a run with GET /runs/{run_id}."""

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
    calls: int | None = Field(
        default=None, description="Number of LLM calls the run made."
    )
    duration_ms: int | None = None


class RunListResponse(BaseModel):
    """The /runs index: one summary row per run, in run order. Each carries
    its id and outcome; fetch a run's full calls via GET /runs/{run_id}."""

    runs: list[RunSummaryResponse]


class AgentRunListResponse(BaseModel):
    """A spawned sub-agent's runs index: the same per-run summaries as
    /runs, plus the agent's own `agent.json` (spawner, task, parentage)."""

    agent: dict | None = Field(
        default=None,
        description="The agent's agent.json — spawner, task, parent linkage.",
    )
    runs: list[RunSummaryResponse]
