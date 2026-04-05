import asyncio
from typing import Literal, Dict

from pydantic import BaseModel, Field

from config import settings
from llm import LLM, Message, Tool


class GetWeatherArgs(BaseModel):
    """Get the current weather for a city."""

    city: str = Field(..., description="City name, e.g. 'San Francisco'")
    units: Literal["celsius", "fahrenheit"] = "celsius"

    @classmethod
    def invoke(cls, args: Dict) -> int:
        cls(**args)
        return 20


tool_registry = {
    "get_weather": GetWeatherArgs,
}


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

    # Tool calling — schema generated from a Pydantic model.
    print("\n--- tool ---")
    weather_tool = Tool.from_model(GetWeatherArgs, name="get_weather")
    messages = [
        Message(
            role="user", content="What's the weather in San Francisco in celsius?"
        )
    ]
    tool_resp = await llm.generate(
        messages=messages,
        tools=[weather_tool],
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
        for tc in tool_resp.tool_calls:
            tool_cls = tool_registry[tc.name]
            res = str(tool_cls.invoke(tc.arguments))
            messages.append(
                Message(
                    role="tool",
                    tool_call_id=tc.id,
                    content=res,
                )
            )
    else:
        print(tool_resp.text)
    
    final_resp = await llm.generate(
        messages=messages,
        tools=[weather_tool],
        tool_choice="auto",
    )
    print(final_resp)


if __name__ == "__main__":
    asyncio.run(main())
