from unittest.mock import AsyncMock

from pydantic import BaseModel

from agent import Agent, Context
from llm.types import GenerateResponse, Message, ToolCall, Usage
from tools.base import BaseTool
from tools.context import ToolContext


class _EmptyInput(BaseModel):
    pass


class _StubTool(BaseTool[_EmptyInput, str]):
    """Minimal concrete tool for agent tests."""

    name = "test_tool"
    input_schema = _EmptyInput

    async def invoke(self, args: _EmptyInput, ctx: ToolContext) -> str:
        return "stub_result"


def _make_llm(**overrides):
    """Create a mock LLM with sensible defaults."""
    llm = AsyncMock()
    llm.generate = AsyncMock(**overrides)
    return llm


def _make_tool(name: str = "test_tool") -> BaseTool:
    """Create a stub BaseTool with the given name."""
    tool = _StubTool()
    # Override the class-level name for this instance
    type(tool).name = name  # type: ignore[assignment]
    return tool


async def test_terminates_when_no_tool_calls():
    llm = _make_llm(
        return_value=GenerateResponse(text="Hello!", tool_calls=None)
    )
    agent = Agent(llm=llm, tools=[])
    context = Context(system_prompt="sys")
    context.add(Message(role="user", content="hi"))

    messages = [msg async for msg in agent.run(context)]

    assert len(messages) == 1
    assert messages[0].role == "assistant"
    assert messages[0].content == "Hello!"


async def test_max_turns_respected():
    """If the model always returns tool calls, the loop stops at max_turns."""
    llm = _make_llm(
        return_value=GenerateResponse(
            text="calling",
            tool_calls=[ToolCall(id="tc_1", name="test_tool", arguments={})],
        )
    )
    tool = _make_tool("test_tool")
    agent = Agent(llm=llm, tools=[tool], max_turns=2)

    context = Context()
    context.add(Message(role="user", content="go"))

    messages = [msg async for msg in agent.run(context)]

    # Each turn: 1 assistant + 1 tool result = 2 messages per turn, 2 turns = 4
    assert len(messages) == 4
    assert llm.generate.call_count == 2


async def test_tool_calls_dispatched_and_yielded():
    """Tool calls are dispatched and results appear in the yielded messages."""
    responses = [
        GenerateResponse(
            text="let me check",
            tool_calls=[ToolCall(id="tc_1", name="test_tool", arguments={})],
        ),
        GenerateResponse(text="The answer is 42.", tool_calls=None),
    ]
    llm = _make_llm(side_effect=responses)
    tool = _make_tool("test_tool")
    agent = Agent(llm=llm, tools=[tool])

    context = Context()
    context.add(Message(role="user", content="question"))

    messages = [msg async for msg in agent.run(context)]

    # Turn 1: assistant + tool result. Turn 2: assistant (no tools). Total: 3
    assert len(messages) == 3
    assert messages[0].role == "assistant"
    assert messages[1].role == "tool"
    assert messages[2].role == "assistant"
    assert messages[2].content == "The answer is 42."


async def test_context_store_matches_yielded():
    """After run(), the context store contains exactly the yielded messages
    plus the original user message."""
    llm = _make_llm(
        return_value=GenerateResponse(text="done", tool_calls=None)
    )
    agent = Agent(llm=llm, tools=[])

    context = Context()
    context.add(Message(role="user", content="hi"))

    yielded = [msg async for msg in agent.run(context)]

    # Store: user + assistant = 2
    assert len(context.store) == 2
    assert context.store.messages[0].role == "user"
    assert context.store.messages[1] == yielded[0]


async def test_on_usage_callback_called_per_api_call():
    """on_usage is called once per LLM.generate() call with the usage."""
    u1 = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    u2 = Usage(prompt_tokens=20, completion_tokens=10, total_tokens=30)

    responses = [
        GenerateResponse(
            text="calling",
            tool_calls=[
                ToolCall(id="tc_1", name="test_tool", arguments={})
            ],
            usage=u1,
        ),
        GenerateResponse(text="done", tool_calls=None, usage=u2),
    ]
    llm = _make_llm(side_effect=responses)
    tool = _make_tool("test_tool")
    agent = Agent(llm=llm, tools=[tool])

    context = Context()
    context.add(Message(role="user", content="go"))

    collected: list[Usage] = []
    async for _msg in agent.run(
        context, on_usage=collected.append
    ):
        pass

    assert len(collected) == 2
    assert collected[0] == u1
    assert collected[1] == u2


async def test_on_usage_not_called_when_none():
    """on_usage is not called if resp.usage is None."""
    llm = _make_llm(
        return_value=GenerateResponse(
            text="hi", tool_calls=None, usage=None
        )
    )
    agent = Agent(llm=llm, tools=[])

    context = Context()
    context.add(Message(role="user", content="hi"))

    collected: list[Usage] = []
    async for _msg in agent.run(
        context, on_usage=collected.append
    ):
        pass

    assert len(collected) == 0
