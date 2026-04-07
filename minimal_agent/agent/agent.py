"""Agent — owns the decide-act-observe loop.

Stateless per-run: the same Agent instance can drive multiple conversations
by accepting different Contexts.
"""

from collections.abc import AsyncGenerator, Callable
from typing import Optional

from llm import LLM, Message, Role
from llm.types import LLMTool, Usage
from tools import ToolContext, dispatch
from tools.base import BaseTool

from .context import Context

OnUsageCallback = Callable[[Usage], None]


class Agent:
    def __init__(
        self,
        llm: LLM,
        tools: list[BaseTool],
        *,
        max_turns: int = 10,
    ) -> None:
        self._llm = llm
        self._tools_by_name: dict[str, BaseTool] = {t.name: t for t in tools}
        self._llm_tools: list[LLMTool] = [t.as_llm_tool() for t in tools]
        self._max_turns = max_turns

    async def run(
        self,
        context: Context,
        *,
        on_usage: Optional[OnUsageCallback] = None,
    ) -> AsyncGenerator[Message, None]:
        """Run the agent loop, yielding each message as it's produced.

        The loop:
        1. Call LLM with context.get_messages() + tool schemas.
        2. Yield the assistant message.
        3. If tool calls present, dispatch each one, yield results.
        4. Repeat until no tool calls or max_turns exhausted.

        Callbacks:
            on_usage: Called with the Usage from each LLM API call.
        """
        for _turn in range(self._max_turns):
            ctx = ToolContext()

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
