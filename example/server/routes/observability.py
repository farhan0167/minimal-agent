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
    RunView,
    ScopeView,
    read_call_records,
    read_events,
    reconstruct_call,
    session_runs,
    session_tree,
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
    ScopeViewResponse,
    SpawnedAgentInfo,
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


def _run_response(run: RunView) -> RunViewResponse:
    return RunViewResponse(
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
                        children=t.children,
                    )
                    for t in call.tool_executions
                ],
                spawned_agents=[
                    SpawnedAgentInfo(
                        agent_id=a.agent_id,
                        spawned_by=a.spawned_by,
                        task=a.task,
                        tool_call_id=a.tool_call_id,
                        status=a.status,
                        duration_ms=a.duration_ms,
                        usage=a.usage,
                    )
                    for a in call.spawned_agents
                ],
            )
            for call in run.calls
        ],
    )


def _scope_response(scope: ScopeView) -> ScopeViewResponse:
    return ScopeViewResponse(
        agent=scope.agent,
        runs=[_run_response(run) for run in scope.runs],
        children=[_scope_response(child) for child in scope.children],
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

    return RunListResponse(runs=[_run_response(run) for run in runs])


@router.get("/{session_id}/tree", response_model=ScopeViewResponse)
async def session_tree_route(session_id: str):
    """The whole recording tree: the session root's runs plus every nested
    agent's, recursively — the complete record of everything every agent
    in the session did."""
    try:
        tree = session_tree(_session_dir(session_id))
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=422, detail=f"Session not reconstructible: {e}"
        ) from e

    return _scope_response(tree)


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
