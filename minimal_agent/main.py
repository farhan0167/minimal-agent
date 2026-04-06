import asyncio
from collections.abc import AsyncGenerator

from config import settings
from llm import LLM, Message
from llm.types import LLMTool
from tools import ToolContext, dispatch
from tools.base import BaseTool
from tools.builtin.get_weather import GetWeather


async def agent_loop(
    llm: LLM,
    messages: list[Message],
    llm_tools: list[LLMTool],
    tools_by_name: dict[str, BaseTool],
    max_turns: int = 10,
) -> AsyncGenerator[Message, None]:
    if max_turns <= 0:
        return

    ctx = ToolContext()
    resp = await llm.generate(messages=messages, tools=llm_tools, tool_choice="auto")

    assistant_msg = Message(
        role="assistant", content=resp.text, tool_calls=resp.tool_calls
    )
    messages.append(assistant_msg)
    yield assistant_msg

    if not resp.tool_calls:
        return

    for tc in resp.tool_calls:
        result_msg = await dispatch(tc, tools_by_name, ctx)
        messages.append(result_msg)
        yield result_msg

    async for msg in agent_loop(
        llm, messages, llm_tools, tools_by_name, max_turns - 1
    ):
        yield msg


async def main():
    llm = LLM(
        model=settings.LLM_MODEL,
        backend=settings.LLM_BACKEND,
        timeout=settings.OPENAI_TIMEOUT,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )

    tools = [GetWeather()]
    tools_by_name = {t.name: t for t in tools}
    llm_tools = [t.as_llm_tool() for t in tools]

    user_input = input("> ")
    messages = [Message(role="user", content=user_input)]

    async for msg in agent_loop(llm, messages, llm_tools, tools_by_name):
        if msg.role == "assistant":
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    print(f"[tool call] {tc.name}({tc.arguments})")
            if msg.content:
                print(f"[assistant] {msg.content}")
        elif msg.role == "tool":
            print(f"[tool result] {msg.content}")


if __name__ == "__main__":
    asyncio.run(main())
