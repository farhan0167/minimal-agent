import asyncio

from config import settings
from llm import LLM, Message
from tools import ToolContext, dispatch
from tools.builtin.get_weather import GetWeather


async def main():
    llm = LLM(
        model=settings.LLM_MODEL,
        backend=settings.LLM_BACKEND,
        timeout=settings.OPENAI_TIMEOUT,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )

    # Wire tools once at startup. `tools_by_name` is the dispatcher's lookup
    # table; `llm_tools` is the schema projection the LLM facade ships to the
    # model.
    tools = [GetWeather()]
    tools_by_name = {t.name: t for t in tools}
    llm_tools = [t.as_llm_tool() for t in tools]

    print("\n--- tool ---")
    messages = [
        Message(role="user", content="What's the weather in San Francisco in celsius?")
    ]
    tool_resp = await llm.generate(
        messages=messages,
        tools=llm_tools,
        tool_choice="auto",
    )

    if tool_resp.tool_calls:
        messages.append(
            Message(
                role="assistant",
                content=tool_resp.text,
                tool_calls=tool_resp.tool_calls,
            )
        )
        ctx = ToolContext()
        for tc in tool_resp.tool_calls:
            result_msg = await dispatch(tc, tools_by_name, ctx)
            messages.append(result_msg)
    else:
        print(tool_resp.text)

    final_resp = await llm.generate(
        messages=messages,
        tools=llm_tools,
        tool_choice="auto",
    )
    print(final_resp)


if __name__ == "__main__":
    asyncio.run(main())
