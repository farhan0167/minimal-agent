"""Session CRUD routes."""

import shutil

from fastapi import APIRouter, HTTPException

from app import (
    create_session,
    get_sessions_dir,
    load_session,
    validate_workspace,
)
from minimal_agent.agent import Session
from schemas import (
    CreateSessionRequest,
    SessionListResponse,
    SessionResponse,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _session_response(session: Session) -> SessionResponse:
    return SessionResponse(
        session_id=session.session_id,
        workspace_root=session._meta.workspace_root,
        model=session.model,
        backend=session.backend,
        created_at=session.created_at,
        updated_at=session.updated_at,
        usage=session.usage.model_dump() if session.usage else None,
    )


@router.post("", status_code=201, response_model=SessionResponse)
async def create_session_route(req: CreateSessionRequest):
    try:
        workspace = validate_workspace(req.workspace_root)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    session = await create_session(
        workspace=workspace,
        model=req.model,
        backend=req.backend,
    )
    return _session_response(session)


@router.get("", response_model=SessionListResponse)
async def list_sessions_route():
    sessions = Session.list_sessions(base_dir=get_sessions_dir())
    return SessionListResponse(
        sessions=[
            SessionResponse(
                session_id=s.session_id,
                workspace_root=s.workspace_root,
                model=s.model,
                backend=s.backend,
                created_at=s.created_at,
                updated_at=s.updated_at,
                usage=s.usage.model_dump() if s.usage else None,
            )
            for s in sessions
        ]
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session_route(session_id: str):
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_response(session)


@router.delete("/{session_id}", status_code=204)
async def delete_session_route(session_id: str):
    session_dir = get_sessions_dir() / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    shutil.rmtree(session_dir)
