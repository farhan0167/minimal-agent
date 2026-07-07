"""Server config route — the facts a UI needs before creating a session."""

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Depends

from ...agent import Agent
from ..deps import get_agents
from ..schemas import AgentInfo, ConfigResponse
from ..service import display_name

router = APIRouter(tags=["config"])


def _version() -> str:
    try:
        return version("minimal-agent")
    except PackageNotFoundError:
        return "unknown"


@router.get("/config", response_model=ConfigResponse)
async def get_config(agents: dict[str, Agent] = Depends(get_agents)):
    return ConfigResponse(
        version=_version(),
        agents=[
            AgentInfo(
                name=name,
                display_name=display_name(name),
                workspace_root=(
                    str(agent.workspace_root) if agent.workspace_root else None
                ),
                model=agent.llm.model,
                backend=str(agent.llm.backend),
                tools=[t.name for t in agent.tools],
            )
            for name, agent in agents.items()
        ],
        default_agent=next(iter(agents)) if len(agents) == 1 else None,
    )
