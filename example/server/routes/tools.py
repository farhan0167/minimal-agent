"""Tool listing route — scoped to agent type."""

from fastapi import APIRouter

from agents import get_agent_config
from schemas import ToolInfo, ToolListResponse

router = APIRouter(tags=["tools"])


@router.get("/tools", response_model=ToolListResponse)
async def list_tools(agent_type: str):
    config = get_agent_config(agent_type)
    return ToolListResponse(tools=[ToolInfo(name=n) for n in config.get_tool_names()])
