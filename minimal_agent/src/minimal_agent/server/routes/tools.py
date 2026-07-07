"""Tool listing route — scoped to a registered agent."""

from fastapi import APIRouter, Depends, HTTPException

from ...agent import Agent
from ..deps import get_agents
from ..schemas import ToolInfo, ToolListResponse
from ..service import UnknownAgentError, resolve_agent

router = APIRouter(tags=["tools"])


@router.get("/tools", response_model=ToolListResponse)
async def list_tools(
    agent: str | None = None,
    agents: dict[str, Agent] = Depends(get_agents),
):
    try:
        _, resolved = resolve_agent(agents, agent)
    except UnknownAgentError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return ToolListResponse(tools=[ToolInfo(name=t.name) for t in resolved.tools])
