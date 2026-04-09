"""The `spawn_agents` tool — spins up sub-agents to work concurrently.

The orchestrator LLM decides how many sub-agents to spawn, what each one
does, and which tools each gets. Sub-agents are ephemeral: they run to
completion inside the tool call, have their own isolated context, and
return their final answer as the tool result.

Sub-agents cannot spawn further sub-agents (no recursion).
"""

import asyncio
from pathlib import Path

from agent import Agent, Context
from llm import LLM
from llm.types import Message, Role
from tools.base import BaseTool
from tools.context import ToolContext

from .schema import SpawnAgentsInput, SubAgentSpec

_SUB_AGENT_PROMPT_PATH = Path(__file__).resolve().parent / "sub_agent.md"


class SpawnAgents(BaseTool[SpawnAgentsInput, str]):
    """Spawn concurrent sub-agents, each with its own context and tool set."""

    name = "spawn_agents"
    input_schema = SpawnAgentsInput

    def __init__(
        self,
        *,
        llm: LLM,
        available_tools: dict[str, BaseTool],
        workspace_root: Path,
    ) -> None:
        self._llm = llm
        self._available_tools = available_tools
        self._workspace_root = workspace_root

    async def invoke(
        self, args: SpawnAgentsInput, ctx: ToolContext
    ) -> str:
        tasks = [
            self._run_sub_agent(i, spec) for i, spec in enumerate(args.agents)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        parts: list[str] = []
        for i, result in enumerate(results):
            spec = args.agents[i]
            header = f"[Sub-agent {i + 1}: {spec.task}]"
            if isinstance(result, BaseException):
                parts.append(f"{header}\nERROR: {type(result).__name__}: {result}")
            else:
                parts.append(f"{header}\n{result}")

        return "\n\n---\n\n".join(parts)

    async def _run_sub_agent(self, index: int, spec: SubAgentSpec) -> str:
        """Build and run a single sub-agent to completion."""
        tools = self._resolve_tools(spec.tools)

        agent = Agent(
            llm=self._llm,
            tools=tools,
            prompt=_SUB_AGENT_PROMPT_PATH.read_text().format(task=spec.task),
            max_turns=spec.max_turns,
        )

        system_prompt = await agent.build_system_prompt(self._workspace_root)
        context = Context(system_prompt=system_prompt)
        context.add(Message(role=Role.USER, content=spec.task))

        last_assistant = ""
        async for msg in agent.run(context):
            if msg.role == Role.ASSISTANT and msg.content:
                last_assistant = msg.content

        return last_assistant or "(sub-agent produced no output)"

    def _resolve_tools(self, tool_names: list[str] | None) -> list[BaseTool]:
        """Select tools for a sub-agent.

        If tool_names is None, give all available tools except spawn_agents
        (preventing recursion). If explicit names are given, filter to those.
        Unknown names are silently skipped.
        """
        if tool_names is None:
            return [
                t
                for name, t in self._available_tools.items()
                if name != self.name
            ]
        return [
            self._available_tools[name]
            for name in tool_names
            if name in self._available_tools and name != self.name
        ]
