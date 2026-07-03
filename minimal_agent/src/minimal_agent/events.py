"""Event seam — typed events, the envelope, and the session-scoped emitter.

One emitter, N sinks: producers call `emit(event)`; the emitter stamps an
envelope (schema version, UTC timestamp, run/call ids) and fans out to every
sink. Emission is fire-and-forget — `emit()` never raises and never blocks on
anything slower than a buffered file append, so the observability layer
cannot kill, stall, or alter a run.

Lives at the package top level (like `context_sources.py`, for the same
reason): both `agent/` and `tools/` emit events, and `tools/` must not
import from `agent/`.

See [.claude/specifications/observability.md](.claude/specifications/observability.md).
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import ClassVar, Protocol, Union
from uuid import uuid4

from .llm.types import Message

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    SESSION_CREATED = "session.created"
    SESSION_LOADED = "session.loaded"
    RUN_START = "run.start"
    RUN_END = "run.end"
    CALL_REQUEST = "call.request"
    CALL_RESPONSE = "call.response"
    TOOL_START = "tool.start"
    TOOL_END = "tool.end"
    SOURCE_FAILED = "source.failed"


class RunEndStatus(StrEnum):
    COMPLETED = "completed"  # model produced no tool calls
    MAX_TURNS = "max_turns"  # loop budget exhausted
    ABANDONED = "abandoned"  # consumer closed the generator (disconnect)
    ERROR = "error"  # an exception escaped the loop


class ToolStatus(StrEnum):
    OK = "ok"
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGS = "invalid_args"
    VALIDATION_FAILED = "validation_failed"
    PERMISSION_ERROR = "permission_error"
    DENIED = "denied"
    ERROR = "error"


@dataclass(frozen=True)
class InjectedBlock:
    """One block of live content injected into an assembled message list.

    `text` is verbatim what assembly produced — framing included — so
    reconstruction is pure data, immune to code drift in framing constants.
    """

    # Store index of the user message the text was merged into;
    # None ⇒ the text was a standalone trailing carrier's full content.
    anchor: int | None
    text: str


@dataclass(frozen=True)
class SessionCreated:
    type: ClassVar[EventType] = EventType.SESSION_CREATED


@dataclass(frozen=True)
class SessionLoaded:
    type: ClassVar[EventType] = EventType.SESSION_LOADED
    message_count: int
    # Healing actions taken at load, e.g. "synthetic_tool_result:call_abc".
    healed: list[str]


@dataclass(frozen=True)
class RunStart:
    type: ClassVar[EventType] = EventType.RUN_START
    model: str
    backend: str
    tools_json: str  # canonical JSON: sorted by name, compact separators
    store_len: int  # store size when the run began


@dataclass(frozen=True)
class RunEnd:
    type: ClassVar[EventType] = EventType.RUN_END
    status: RunEndStatus
    calls: int
    duration_ms: int


@dataclass(frozen=True)
class CallRequest:
    type: ClassVar[EventType] = EventType.CALL_REQUEST
    projected: list[tuple[int, int]]  # [start, end) store-index ranges
    store_len: int  # ⇒ the reply lands at this index
    system_prompt: str | None  # raw text; blob-interned by CallLogSink
    injected_run: InjectedBlock | None
    injected_call: InjectedBlock | None
    assembled_sha256: str


@dataclass(frozen=True)
class CallResponse:
    type: ClassVar[EventType] = EventType.CALL_RESPONSE
    latency_ms: int
    usage: dict | None  # Usage.model_dump(); None if backend omitted it
    tool_calls: int  # how many the model requested


@dataclass(frozen=True)
class ToolStart:
    type: ClassVar[EventType] = EventType.TOOL_START
    tool_call_id: str
    # Args are NOT copied — they live in the transcript's assistant message.
    name: str


@dataclass(frozen=True)
class ToolEnd:
    type: ClassVar[EventType] = EventType.TOOL_END
    tool_call_id: str
    name: str
    status: ToolStatus
    duration_ms: int


@dataclass(frozen=True)
class SourceFailed:
    type: ClassVar[EventType] = EventType.SOURCE_FAILED
    source: str  # source.name
    # Exception type name only — messages can carry paths/secrets.
    error: str


Event = Union[
    SessionCreated,
    SessionLoaded,
    RunStart,
    RunEnd,
    CallRequest,
    CallResponse,
    ToolStart,
    ToolEnd,
    SourceFailed,
]


@dataclass(frozen=True)
class Envelope:
    """The wrapper the emitter stamps around each event."""

    v: int  # envelope schema version
    ts: str  # UTC ISO-8601 with a `Z` suffix, stamped by the emitter
    run_id: str | None  # None for session-scoped events
    call_id: str | None  # None for run/session-scoped events
    event: Event


class Sink(Protocol):
    def handle(self, env: Envelope) -> None: ...


# Call-scoped events are stamped with the current call id.
_CALL_SCOPED = {
    EventType.CALL_REQUEST,
    EventType.CALL_RESPONSE,
    EventType.TOOL_START,
    EventType.TOOL_END,
}

_ENVELOPE_VERSION = 1


def _utc_now() -> str:
    return (
        datetime.now(tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class EventEmitter:
    """Session-scoped fan-out point.

    Fire-and-forget: emit() never raises — a sink failure is logged and
    skipped, and one sink failing never starves another. Owns id minting:
    run ids on run.start, call numbering on call.request. Ids need no
    persistence: run ids are random (resume-safe by construction), call
    ids derive from them.
    """

    def __init__(self, sinks: list[Sink]) -> None:
        self._sinks = sinks
        self._run_id: str | None = None
        self._call_no = 0

    def emit(self, event: Event) -> None:
        if isinstance(event, RunStart):
            self._run_id = "r-" + uuid4().hex[:8]
            self._call_no = 0
        elif isinstance(event, CallRequest):
            if self._run_id is None:  # direct assemble() with no run.start
                self._run_id = "r-" + uuid4().hex[:8]  # degrade sanely
            self._call_no += 1

        env = Envelope(
            v=_ENVELOPE_VERSION,
            ts=_utc_now(),
            run_id=self._run_id,
            call_id=(
                f"{self._run_id}:c{self._call_no}"
                if event.type in _CALL_SCOPED
                else None
            ),
            event=event,
        )
        for sink in self._sinks:
            try:
                sink.handle(env)
            except Exception:
                logger.debug("event sink %r failed; continuing", sink, exc_info=True)


def hash_messages(msgs: list[Message]) -> str:
    """Canonical digest of an assembled message list.

    Computed over `model_dump_json()` output — a Pydantic upgrade or a new
    `Message` field changes the serialization, so a mismatch on records
    written under an older environment means *unverifiable*, not *tampered*.
    """
    digest = hashlib.sha256(
        "\n".join(m.model_dump_json() for m in msgs).encode()
    ).hexdigest()
    return f"sha256:{digest}"
