"""Session CRUD routes."""

import shutil

from fastapi import APIRouter, Depends, HTTPException

from ...agent import Agent, Session, SessionManager, SessionMeta
from ..deps import get_agents, get_manager
from ..schemas import CreateSessionRequest, SessionListResponse, SessionResponse
from ..service import (
    UnknownAgentError,
    create_session,
    load_agent_name,
    open_session_readonly,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _agent_name_or_none(manager: SessionManager, session_id: str) -> str | None:
    """Sessions written by other consumers of the store have no sidecar —
    list/get views tolerate that instead of failing the whole response."""
    try:
        return load_agent_name(manager, session_id)
    except FileNotFoundError:
        return None


def _session_response(
    session: Session | SessionMeta, agent: str | None
) -> SessionResponse:
    return SessionResponse(
        session_id=session.session_id,
        workspace_root=session.workspace_root,
        agent=agent,
        model=session.model,
        backend=session.backend,
        created_at=session.created_at,
        updated_at=session.updated_at,
        usage=session.usage.model_dump() if session.usage else None,
    )


@router.post("", status_code=201, response_model=SessionResponse)
async def create_session_route(
    req: CreateSessionRequest,
    agents: dict[str, Agent] = Depends(get_agents),
    manager: SessionManager = Depends(get_manager),
):
    try:
        name, session = await create_session(agents, manager, req.agent)
    except UnknownAgentError as e:
        # No name on a multi-agent App is a malformed request; a name that
        # isn't registered is a missing resource.
        raise HTTPException(
            status_code=422 if req.agent is None else 404, detail=str(e)
        ) from e
    except ValueError as e:
        # e.g. the agent was constructed without a workspace_root.
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _session_response(session, agent=name)


@router.get("", response_model=SessionListResponse)
async def list_sessions_route(manager: SessionManager = Depends(get_manager)):
    return SessionListResponse(
        sessions=[
            _session_response(meta, agent=_agent_name_or_none(manager, meta.session_id))
            for meta in manager.list_sessions()
        ]
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session_route(
    session_id: str,
    manager: SessionManager = Depends(get_manager),
):
    try:
        session = open_session_readonly(manager, session_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Session not found") from e
    return _session_response(session, agent=_agent_name_or_none(manager, session_id))


@router.delete("/{session_id}", status_code=204)
async def delete_session_route(
    session_id: str,
    manager: SessionManager = Depends(get_manager),
):
    session_dir = manager.base_dir / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    shutil.rmtree(session_dir)
