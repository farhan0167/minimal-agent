"""Observability routes — the session's event trace and call audit.

Read-only views over the artifacts the framework records next to
messages.jsonl: the timeline (events.jsonl), the audit records
(calls.jsonl), on-demand byte-exact reconstruction of what the model saw
on any recorded call, and the holistic runs view that joins all of it.
"""

from fastapi import APIRouter, HTTPException
from minimal_agent.audit import (
    CallRecordNotFoundError,
    ReconstructedCall,
    read_call_records,
    read_events,
    reconstruct_call,
    session_runs,
)

from app import get_sessions_dir
from schemas import (
    CallRecordListResponse,
    CallViewResponse,
    EventListResponse,
    MessageResponse,
    ReconstructedCallResponse,
    RunListResponse,
    RunViewResponse,
    ToolExecutionInfo,
)

router = APIRouter(prefix="/sessions", tags=["observability"])


def _session_dir(session_id: str):
    session_dir = get_sessions_dir() / session_id
    if not session_dir.is_dir():
        raise HTTPException(status_code=404, detail="Session not found")
    return session_dir


def _reconstructed_response(result: ReconstructedCall) -> ReconstructedCallResponse:
    return ReconstructedCallResponse(
        call_id=result.call_id,
        run_id=result.run_id,
        ts=result.ts,
        model=result.model,
        backend=result.backend,
        verified=result.verified,
        recorded_sha256=result.recorded_sha256,
        computed_sha256=result.computed_sha256,
        tools=result.tools,
        messages=[MessageResponse(**m.model_dump()) for m in result.messages],
    )


@router.get("/{session_id}/events", response_model=EventListResponse)
async def list_events_route(session_id: str):
    """The session timeline: what happened, in order, with timestamps."""
    return EventListResponse(events=read_events(_session_dir(session_id)))


@router.get("/{session_id}/calls", response_model=CallRecordListResponse)
async def list_calls_route(session_id: str):
    """The raw audit records — one per LLM call, joined to the timeline
    by call_id."""
    return CallRecordListResponse(calls=read_call_records(_session_dir(session_id)))


@router.get("/{session_id}/runs", response_model=RunListResponse)
async def list_runs_route(session_id: str):
    """The holistic view: every model input and output, by run and call.

    Each call carries its full reconstructed input, its response, latency,
    usage, and tool executions. Deliberately eager — this is a cold-path
    debug read, so everything comes back in one response.
    """
    try:
        runs = session_runs(_session_dir(session_id))
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=422, detail=f"Session not reconstructible: {e}"
        ) from e

    return RunListResponse(
        runs=[
            RunViewResponse(
                run_id=run.run_id,
                started_at=run.started_at,
                model=run.model,
                backend=run.backend,
                status=run.status,
                duration_ms=run.duration_ms,
                calls=[
                    CallViewResponse(
                        call_id=call.call_id,
                        ts=call.ts,
                        input=_reconstructed_response(call.input),
                        response=(
                            MessageResponse(**call.response.model_dump())
                            if call.response
                            else None
                        ),
                        latency_ms=call.latency_ms,
                        usage=call.usage,
                        tool_executions=[
                            ToolExecutionInfo(
                                tool_call_id=t.tool_call_id,
                                name=t.name,
                                status=t.status,
                                duration_ms=t.duration_ms,
                            )
                            for t in call.tool_executions
                        ],
                    )
                    for call in run.calls
                ],
            )
            for run in runs
        ]
    )


@router.get(
    "/{session_id}/calls/{call_id}",
    response_model=ReconstructedCallResponse,
)
async def reconstruct_call_route(session_id: str, call_id: str):
    """Rebuild, byte-exactly, what the model saw on one recorded call."""
    session_dir = _session_dir(session_id)
    try:
        result = reconstruct_call(session_dir, call_id)
    except CallRecordNotFoundError as e:
        raise HTTPException(status_code=404, detail="Call record not found") from e
    except FileNotFoundError as e:
        # A referenced blob is missing (e.g. a dangling ref from a failed
        # write) — the record exists but cannot be rebuilt.
        raise HTTPException(
            status_code=422, detail=f"Record not reconstructible: {e}"
        ) from e

    return _reconstructed_response(result)
