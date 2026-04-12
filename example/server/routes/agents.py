"""Agent listing route."""

from fastapi import APIRouter

from agents import list_agents

router = APIRouter(tags=["agents"])


@router.get("/agents")
async def list_agents_route():
    return {"agents": list_agents()}
