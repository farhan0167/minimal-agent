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
        session_id="20260407-042555-5e1f",
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
