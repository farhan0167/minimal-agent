"""Research agent — web search and read-only file tools."""

from pathlib import Path

from minimal_agent.agent import Agent
from minimal_agent.config import Backend, settings
from minimal_agent.llm import LLM
from minimal_agent.tools.builtin.glob import Glob
from minimal_agent.tools.builtin.grep import Grep
from minimal_agent.tools.builtin.read_file import ReadFile
from minimal_agent.tools.builtin.web_extract import WebExtract
from minimal_agent.tools.builtin.web_search import WebSearch


_TOOL_CLASSES = [
    ReadFile,
    Grep,
    Glob,
    WebSearch,
    WebExtract,
]


class ResearchAgentConfig:
    name = "research"
    display_name = "Research Assistant"

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

        tools = [
            ReadFile(workspace_root=workspace, read_timestamps=read_timestamps),
            Grep(workspace_root=workspace),
            Glob(workspace_root=workspace),
            WebSearch(),
            WebExtract(),
        ]

        return Agent(llm=llm, tools=tools, workspace_root=workspace)


config = ResearchAgentConfig()
