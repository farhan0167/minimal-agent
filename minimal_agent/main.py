import asyncio
from pathlib import Path

from agent import Agent, Session
from config import settings
from llm import LLM, Message, Role
from tools.builtin.get_weather import GetWeather
from tools.builtin.glob import Glob
from tools.builtin.grep import Grep
from tools.builtin.read_file import ReadFile
from tools.builtin.run_shell import RunShell
from tools.builtin.write_file import WriteFile


async def main():
    llm = LLM(
        model=settings.LLM_MODEL,
        backend=settings.LLM_BACKEND,
        timeout=settings.OPENAI_TIMEOUT,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )

    read_timestamps: dict[str, float] = {}
    agent = Agent(
        llm=llm,
        tools=[
            GetWeather(),
            ReadFile(
                workspace_root=Path.cwd(),
                read_timestamps=read_timestamps,
            ),
            WriteFile(
                workspace_root=Path.cwd(),
                read_timestamps=read_timestamps,
            ),
            RunShell(workspace_root=Path.cwd()),
            Grep(workspace_root=Path.cwd()),
            Glob(workspace_root=Path.cwd()),
        ],
    )

    sessions_dir = Path(settings.SESSIONS_DIR)
    # session = Session.create(
    #     model=settings.LLM_MODEL,
    #     backend=settings.LLM_BACKEND,
    #     system_prompt="You are a helpful assistant.",
    #     base_dir=sessions_dir,
    # )

    # To resume an existing session:
    session = Session.load(
        session_id="20260407-202941-e01d",
        model=settings.LLM_MODEL,
        backend=settings.LLM_BACKEND,
        system_prompt="You are a helpful assistant.",
        base_dir=sessions_dir,
    )

    user_input = input("> ")
    session.context.add(Message(role=Role.USER, content=user_input))

    async for msg in agent.run(
        session.context, on_usage=session.update_usage
    ):
        if msg.role == Role.ASSISTANT:
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    print(f"[tool call] {tc.name}({tc.arguments})")
            if msg.content:
                print(f"[assistant] {msg.content}")
        elif msg.role == Role.TOOL:
            print(f"[tool result] {msg.content}")


if __name__ == "__main__":
    asyncio.run(main())
