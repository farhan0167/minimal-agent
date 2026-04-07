## Starter Code

```python
import asyncio
from typing import Literal

from pydantic import BaseModel, Field

from config import settings
from llm import LLM, LLMTool, Message


class CalendarEvent(BaseModel):
    name: str
    date: str
    participants: list[str]


class GetWeatherArgs(BaseModel):
    """Get the current weather for a city."""

    city: str = Field(..., description="City name, e.g. 'San Francisco'")
    units: Literal["celsius", "fahrenheit"] = "celsius"


async def main():
    # Drop unset values — the SDK rejects None for max_retries/timeout and
    # has its own defaults we want to preserve.
    overrides = {
        "timeout": settings.OPENAI_TIMEOUT,
        "max_retries": settings.OPENAI_MAX_RETRIES,
        "api_key": settings.OPENAI_API_KEY,
    }
    llm = LLM(
        model=settings.LLM_MODEL,
        **{k: v for k, v in overrides.items() if v is not None},
    )

    # Non-streaming
    resp = await llm.generate(
        [
            Message(
                role="user",
                content="Write a one-sentence bedtime story about a unicorn.",
            )
        ],
        system="You are a concise storyteller.",
    )
    print(resp.text)

    # Tool calling — schema generated from a Pydantic model.
    print("\n--- tool ---")
    weather_tool = LLMTool.from_model(GetWeatherArgs, name="get_weather")
    print(f"tool: {weather_tool.name} — {weather_tool.description}")
    tool_resp = await llm.generate(
        [
            Message(
                role="user", content="What's the weather in San Francisco in celsius?"
            )
        ],
        tools=[weather_tool],
        tool_choice="auto",
    )
    if tool_resp.tool_calls:
        for tc in tool_resp.tool_calls:
            print(f"  call: {tc.name}({tc.arguments})")
    else:
        print(tool_resp.text)

    # Structured output
    print("\n--- structured ---")
    structured = await llm.generate_structured(
        [
            Message(
                role="user",
                content="Alice and Bob are going to a science fair on Friday.",
            )
        ],
        schema=CalendarEvent,
        system="Extract the event information.",
    )
    if structured.refusal:
        print(f"refused: {structured.refusal}")
    else:
        print(structured.parsed)

    # Streaming
    print("\n--- streaming ---")
    async for chunk in llm.stream(
        [Message(role="user", content="Count from 1 to 5.")],
    ):
        print(chunk.text, end="", flush=True)
    print()


if __name__ == "__main__":
    asyncio.run(main())
```

## Agent Example

```python
import asyncio
from pathlib import Path

from agent import Agent, Session
from config import settings
from llm import LLM, Message
from tools.builtin.get_weather import GetWeather


async def main():
    llm = LLM(
        model=settings.LLM_MODEL,
        backend=settings.LLM_BACKEND,
        timeout=settings.OPENAI_TIMEOUT,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )

    agent = Agent(llm=llm, tools=[GetWeather()])

    sessions_dir = Path(settings.SESSIONS_DIR)
    # session = Session.create(
    #     model=settings.LLM_MODEL,
    #     backend=settings.LLM_BACKEND,
    #     system_prompt="You are a helpful assistant.",
    #     base_dir=sessions_dir,
    # )

    # To resume an existing session:
    session = Session.load(
        session_id="20260407-044552-0e5e",
        model=settings.LLM_MODEL,
        backend=settings.LLM_BACKEND,
        system_prompt="You are a helpful assistant.",
        base_dir=sessions_dir,
    )

    user_input = input("> ")
    session.context.add(Message(role="user", content=user_input))

    async for msg in agent.run(
        session.context, on_usage=session.update_usage
    ):
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
```