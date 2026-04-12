"""Base interface that every agent module must implement."""

from pathlib import Path
from typing import Protocol

from minimal_agent.agent import Agent


class AgentConfig(Protocol):
    name: str
    display_name: str

    def build_agent(self, workspace: Path, model: str, backend: str) -> Agent: ...

    def get_tool_names(self) -> list[str]: ...
