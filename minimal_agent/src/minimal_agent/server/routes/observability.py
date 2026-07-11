"""Observability routes — the session's event trace and call audit.

Read-only views over the artifacts the framework records next to
messages.jsonl: the timeline (events.jsonl), the audit records
(calls.jsonl), on-demand byte-exact reconstruction of what the model saw
on any recorded call, and the holistic runs view that joins all of it.

A spawned sub-agent records the same artifact kit under its own scope, so
the runs index and per-run view are also served for any agent by id via
the `/agents/{agent_id}/...` routes — the same shapes, one scope down.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ...agent import SessionManager
from ...audit import (
    CallRecordNotFoundError,
    ReconstructedCall,
    RunView,
    find_agent_scope,
    read_agent_meta,
    read_call_records,
    read_events,
    reconstruct_call,
    run_summaries,
    single_run,
)
from ..deps import get_manager
from ..schemas import (
    AgentRunListResponse,
    CallInputResponse,
    CallRecordListResponse,
    CallViewResponse,
    EventListResponse,
    MessageResponse,
    ReconstructedCallResponse,
    RunListResponse,
    RunSummaryResponse,
    RunViewResponse,
    SpawnedAgentInfo,
    ToolExecutionInfo,
)

router = APIRouter(prefix="/sessions", tags=["observability"])


def _session_dir(manager: SessionManager, session_id: str) -> Path:
    session_dir = manager.base_dir / session_id
    if not session_dir.is_dir():
        raise HTTPException(status_code=404, detail="Session not found")
    return session_dir


def _agent_dir(manager: SessionManager, session_id: str, agent_id: str) -> Path:
    """The recording scope of a spawned agent, resolved by id anywhere in the
    session's tree. 404 if the session or the agent is unknown."""
    scope_dir = find_agent_scope(_session_dir(manager, session_id), agent_id)
    if scope_dir is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return scope_dir


def _runs_index(scope_dir: Path) -> list[RunSummaryResponse]:
    """The cheap per-run index for any scope (session root or a sub-agent)."""
    return [
        RunSummaryResponse(
            run_id=s.run_id,
            started_at=s.started_at,
            model=s.model,
            backend=s.backend,
            status=s.status,
            calls=s.calls,
            duration_ms=s.duration_ms,
        )
        for s in run_summaries(scope_dir)
    ]


def _one_run(scope_dir: Path, run_id: str) -> RunViewResponse:
    """One run's full view for any scope; 404 unknown, 422 unreconstructible."""
    try:
        run = single_run(scope_dir, run_id)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=422, detail=f"Run not reconstructible: {e}"
        ) from e
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_response(run)


def _reconstructed_response(result: ReconstructedCall) -> ReconstructedCallResponse:
    """Self-describing single-call payload for GET /calls/{call_id}: the
    run-level fingerprint is inline because there's no run wrapper here."""
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


def _call_input_response(result: ReconstructedCall) -> CallInputResponse:
    """Slim per-call input for the nested run view: the run-level fingerprint
    (model, backend, tools) is on the run object, not repeated here."""
    return CallInputResponse(
        call_id=result.call_id,
        run_id=result.run_id,
        ts=result.ts,
        verified=result.verified,
        recorded_sha256=result.recorded_sha256,
        computed_sha256=result.computed_sha256,
        messages=[MessageResponse(**m.model_dump()) for m in result.messages],
    )


def _run_response(run: RunView) -> RunViewResponse:
    return RunViewResponse(
        run_id=run.run_id,
        started_at=run.started_at,
        model=run.model,
        backend=run.backend,
        tools=run.tools,
        system_prompt=run.system_prompt,
        status=run.status,
        duration_ms=run.duration_ms,
        calls=[
            CallViewResponse(
                call_id=call.call_id,
                ts=call.ts,
                input=_call_input_response(call.input),
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


@router.get("/{session_id}/events", response_model=EventListResponse)
async def list_events_route(
    session_id: str, manager: SessionManager = Depends(get_manager)
):
    """The session timeline: what happened, in order, with timestamps."""
    return EventListResponse(events=read_events(_session_dir(manager, session_id)))


@router.get("/{session_id}/calls", response_model=CallRecordListResponse)
async def list_calls_route(
    session_id: str, manager: SessionManager = Depends(get_manager)
):
    """The raw audit records — one per LLM call, joined to the timeline
    by call_id."""
    return CallRecordListResponse(
        calls=read_call_records(_session_dir(manager, session_id))
    )


@router.get("/{session_id}/runs", response_model=RunListResponse)
async def list_runs_route(
    session_id: str, manager: SessionManager = Depends(get_manager)
):
    """The runs index: one summary row per run — id, model, outcome — in run
    order. Cheap by design (reads runs.jsonl, reconstructs nothing); fetch a
    run's full calls with GET /runs/{run_id}.
    """
    return RunListResponse(runs=_runs_index(_session_dir(manager, session_id)))


@router.get("/{session_id}/runs/{run_id}", response_model=RunViewResponse)
async def get_run_route(
    session_id: str,
    run_id: str,
    manager: SessionManager = Depends(get_manager),
):
    """One run's holistic view — every model input and output for a single
    run_id, joined like /runs but scoped to one run.

    Built for large sessions: reconstructing every run's calls to read just
    one is the slow path this avoids. Prefer this over /runs when you already
    know the run you want.
    """
    return _one_run(_session_dir(manager, session_id), run_id)


@router.get("/{session_id}/agents/{agent_id}/runs", response_model=AgentRunListResponse)
async def list_agent_runs_route(
    session_id: str,
    agent_id: str,
    manager: SessionManager = Depends(get_manager),
):
    """The runs index for a spawned sub-agent, by id — the same cheap per-run
    summary as GET /runs, one scope down. The agent's parentage and outcome
    ride along in `agent`. Fetch a run's full calls with
    GET /agents/{agent_id}/runs/{run_id}.
    """
    scope_dir = _agent_dir(manager, session_id, agent_id)
    return AgentRunListResponse(
        agent=read_agent_meta(scope_dir), runs=_runs_index(scope_dir)
    )


@router.get(
    "/{session_id}/agents/{agent_id}/runs/{run_id}",
    response_model=RunViewResponse,
)
async def get_agent_run_route(
    session_id: str,
    agent_id: str,
    run_id: str,
    manager: SessionManager = Depends(get_manager),
):
    """One run inside a spawned sub-agent — the same holistic per-run view as
    GET /runs/{run_id}, scoped to the agent's own recording."""
    return _one_run(_agent_dir(manager, session_id, agent_id), run_id)


@router.get(
    "/{session_id}/calls/{call_id}",
    response_model=ReconstructedCallResponse,
)
async def reconstruct_call_route(
    session_id: str,
    call_id: str,
    manager: SessionManager = Depends(get_manager),
):
    """Rebuild, byte-exactly, what the model saw on one recorded call."""
    session_dir = _session_dir(manager, session_id)
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
