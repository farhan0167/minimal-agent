"""Agent — owns the decide-act-observe loop.

The Agent owns its identity: behavior prompt, context sources, tools, and
LLM configuration. Sessions are instances of that identity — every session
created by an agent inherits its prompt.
"""

from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Optional, Union

from ..llm import LLM, Message, Role
from ..llm.types import LLMTool, Usage
from ..skills import discover_skills
from ..system_prompt import (
    ContextSource,
    DirectoryTreeSource,
    GitStatusSource,
    SkillsContextSource,
    build_system_prompt,
    load_prompt,
)
from ..tools import ToolContext, dispatch
from ..tools.base import BaseTool
from ..tools.builtin.skill import SkillTool
from ..tools.context import PermissionCallback
from .context import Context

OnUsageCallback = Callable[[Usage], None]

# Default context sources for the built-in software engineering agent.
_DEFAULT_CONTEXT_SOURCES: list[ContextSource] = [
    GitStatusSource(),
    DirectoryTreeSource(),
]


class Agent:
    def __init__(
        self,
        llm: LLM,
        tools: list[BaseTool],
        *,
        prompt: Union[str, Path, None] = None,
        context_sources: list[ContextSource] | None = None,
        max_turns: int = 10,
        workspace_root: Path | None = None,
        enable_skills: bool = True,
    ) -> None:
        self._llm = llm
        self._tools_by_name: dict[str, BaseTool] = {t.name: t for t in tools}
        self._llm_tools: list[LLMTool] = [t.as_llm_tool() for t in tools]
        self._max_turns = max_turns
        self._behavior_prompt = load_prompt(prompt)

        # Default prompt → default context sources.
        # Custom prompt → blank slate (user opts in).
        if context_sources is not None:
            resolved_sources = list(context_sources)
        elif prompt is None:
            resolved_sources = list(_DEFAULT_CONTEXT_SOURCES)
        else:
            resolved_sources = []

        # Skill discovery: scan the filesystem once at construction, register
        # the SkillTool and inject the metadata list into the system prompt.
        if enable_skills and workspace_root is not None:
            skills = discover_skills(workspace_root)
            active = [s for s in skills if s.shadowed_by is None]
            if active:
                skill_tool = SkillTool(skills)
                self._tools_by_name[skill_tool.name] = skill_tool
                self._llm_tools.append(skill_tool.as_llm_tool())
                resolved_sources.append(SkillsContextSource(skills))

        self._context_sources = resolved_sources

    async def build_system_prompt(self, workspace_root: Path) -> str:
        """Build the full system prompt for a new session.

        Combines the behavior prompt, environment block, and context
        blocks from this agent's configured sources.
        """
        return await build_system_prompt(
            behavior_prompt=self._behavior_prompt,
            workspace_root=workspace_root,
            context_sources=self._context_sources,
        )

    async def run(
        self,
        context: Context,
        *,
        on_usage: Optional[OnUsageCallback] = None,
        permission_callback: Optional[PermissionCallback] = None,
    ) -> AsyncGenerator[Message, None]:
        """Run the agent loop, yielding each message as it's produced.

        The loop:
        1. Call LLM with context.get_messages() + tool schemas.
        2. Yield the assistant message.
        3. If tool calls present, dispatch each one, yield results.
        4. Repeat until no tool calls or max_turns exhausted.

        Callbacks:
            on_usage: Called with the Usage from each LLM API call.
            permission_callback: Called when a tool requires user confirmation.
        """
        for _turn in range(self._max_turns):
            ctx = ToolContext(permission_callback=permission_callback)

            resp = await self._llm.generate(
                messages=context.get_messages(),
                tools=self._llm_tools,
                tool_choice="auto",
            )

            if on_usage and resp.usage:
                on_usage(resp.usage)

            assistant_msg = Message(
                role=Role.ASSISTANT,
                content=resp.text,
                tool_calls=resp.tool_calls,
            )
            context.add(assistant_msg)
            yield assistant_msg

            if not resp.tool_calls:
                return

            for tc in resp.tool_calls:
                result_msg = await dispatch(tc, self._tools_by_name, ctx)
                context.add(result_msg)
                yield result_msg
