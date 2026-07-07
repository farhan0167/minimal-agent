"""Agent listing route."""

from fastapi import APIRouter, Depends

from ...agent import Agent
from ..deps import get_agents
from ..service import display_name

router = APIRouter(tags=["agents"])


@router.get("/agents")
async def list_agents_route(agents: dict[str, Agent] = Depends(get_agents)):
    return {
        "agents": [
            {"name": name, "display_name": display_name(name)} for name in agents
        ]
    }
