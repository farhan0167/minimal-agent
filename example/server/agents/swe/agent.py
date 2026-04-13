"""Software engineering agent — all builtin tools."""

from pathlib import Path

from minimal_agent.agent import Agent
from minimal_agent.config import Backend, settings
from minimal_agent.llm import LLM
from minimal_agent.tools.builtin.edit_file import EditFile
from minimal_agent.tools.builtin.get_weather import GetWeather
from minimal_agent.tools.builtin.glob import Glob
from minimal_agent.tools.builtin.grep import Grep
from minimal_agent.tools.builtin.read_file import ReadFile
from minimal_agent.tools.builtin.run_shell import RunShell
from minimal_agent.tools.builtin.spawn_agents import SpawnAgents
from minimal_agent.tools.builtin.web_extract import WebExtract
from minimal_agent.tools.builtin.web_search import WebSearch
from minimal_agent.tools.builtin.write_file import WriteFile


_TOOL_CLASSES = [
    GetWeather,
    ReadFile,
    EditFile,
    WriteFile,
    RunShell,
    Grep,
    Glob,
    WebSearch,
    WebExtract,
    SpawnAgents,
]


class SWEAgentConfig:
    name = "swe"
    display_name = "Software Engineer"

    def get_tool_names(self) -> list[str]:
        return [cls.name for cls in _TOOL_CLASSES]

    def build_agent(self, workspace: Path, model: str, backend: str) -> Agent:
        llm = LLM(
            model=model or settings.LLM_MODEL,
            backend=Backend(backend) if backend else settings.LLM_BACKEND,
            timeout=settings.OPENAI_TIMEOUT,
            max_retries=settings.OPENAI_MAX_RETRIES,
        )

        read_timestamps: dict[str, float] = {}

        builtin_tools = [
            GetWeather(),
            ReadFile(workspace_root=workspace, read_timestamps=read_timestamps),
            EditFile(workspace_root=workspace, read_timestamps=read_timestamps),
            WriteFile(workspace_root=workspace, read_timestamps=read_timestamps),
            RunShell(workspace_root=workspace),
            Grep(workspace_root=workspace),
            Glob(workspace_root=workspace),
            WebSearch(),
            WebExtract(),
        ]

        tools_by_name = {t.name: t for t in builtin_tools}

        spawn_agents = SpawnAgents(
            llm=llm,
            available_tools=tools_by_name,
            workspace_root=workspace,
        )

        return Agent(
            llm=llm,
            tools=[*builtin_tools, spawn_agents],
            workspace_root=workspace,
        )


config = SWEAgentConfig()
