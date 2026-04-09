"""Tool listing route."""

from fastapi import APIRouter

from app import get_tool_names
from schemas import ToolInfo, ToolListResponse

router = APIRouter(tags=["tools"])


@router.get("/tools", response_model=ToolListResponse)
async def list_tools():
    return ToolListResponse(tools=[ToolInfo(name=n) for n in get_tool_names()])
