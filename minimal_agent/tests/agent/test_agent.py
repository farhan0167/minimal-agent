from typing import AsyncIterator, List
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from minimal_agent.agent import Agent, Context
from minimal_agent.agent.session import Session, SessionConfigMismatchError
from minimal_agent.llm.types import (
    GenerateResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolCallDelta,
    Usage,
)
from minimal_agent.tools.base import BaseTool
from minimal_agent.tools.context import ToolContext


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
    context.add(Message(role=Role.USER, content="hi"))

    messages = [msg async for msg in agent.run(context)]

    assert len(messages) == 1
    assert messages[0].role == Role.ASSISTANT
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
    context.add(Message(role=Role.USER, content="go"))

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
    context.add(Message(role=Role.USER, content="question"))

    messages = [msg async for msg in agent.run(context)]

    # Turn 1: assistant + tool result. Turn 2: assistant (no tools). Total: 3
    assert len(messages) == 3
    assert messages[0].role == Role.ASSISTANT
    assert messages[1].role == Role.TOOL
    assert messages[2].role == Role.ASSISTANT
    assert messages[2].content == "The answer is 42."


async def test_context_store_matches_yielded():
    """After run(), the context store contains exactly the yielded messages
    plus the original user message."""
    llm = _make_llm(
        return_value=GenerateResponse(text="done", tool_calls=None)
    )
    agent = Agent(llm=llm, tools=[])

    context = Context()
    context.add(Message(role=Role.USER, content="hi"))

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
    context.add(Message(role=Role.USER, content="go"))

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
    context.add(Message(role=Role.USER, content="hi"))

    collected: list[Usage] = []
    async for _msg in agent.run(
        context, on_usage=collected.append
    ):
        pass

    assert len(collected) == 0


# ---- streaming (run(stream=True)) -----------------------------------------


def _make_streaming_llm(turns: List[List[StreamChunk]]):
    """Mock LLM whose `stream` yields one list of chunks per turn.

    Each call to `llm.stream(...)` returns an async iterator over the next
    turn's chunk list, mirroring how the real facade yields a fresh stream
    per API call.
    """

    async def _gen(chunks: List[StreamChunk]) -> AsyncIterator[StreamChunk]:
        for c in chunks:
            yield c

    calls = iter(turns)

    def _stream(**_kwargs) -> AsyncIterator[StreamChunk]:
        return _gen(next(calls))

    llm = AsyncMock()
    llm.stream = _stream
    return llm


async def test_stream_yields_chunks_then_committed_message():
    """A streaming turn yields each StreamChunk, then the committed Message."""
    llm = _make_streaming_llm(
        [[StreamChunk(text="Hel"), StreamChunk(text="lo!")]]
    )
    agent = Agent(llm=llm, tools=[])
    context = Context(system_prompt="sys")
    context.add(Message(role=Role.USER, content="hi"))

    items = [item async for item in agent.run(context, stream=True)]

    # Two deltas, then one committed assistant Message.
    assert [type(i) for i in items] == [StreamChunk, StreamChunk, Message]
    assert items[-1].role == Role.ASSISTANT
    assert items[-1].content == "Hello!"
    # The committed message — not the deltas — is what lands in the store.
    assert context.store.messages[-1] == items[-1]


async def test_stream_dispatches_accumulated_tool_calls():
    """Tool-call fragments streamed across chunks are reassembled, dispatched,
    and the loop continues to a second (text-only) turn."""
    turn1 = [
        StreamChunk(text="checking"),
        StreamChunk(
            tool_calls=[ToolCallDelta(index=0, id="tc_1", name="test_tool")]
        ),
        StreamChunk(tool_calls=[ToolCallDelta(index=0, arguments="{}")]),
    ]
    turn2 = [StreamChunk(text="done")]
    llm = _make_streaming_llm([turn1, turn2])
    agent = Agent(llm=llm, tools=[_make_tool("test_tool")])

    context = Context()
    context.add(Message(role=Role.USER, content="go"))

    items = [item async for item in agent.run(context, stream=True)]

    messages = [i for i in items if isinstance(i, Message)]
    # Turn 1: assistant + tool result. Turn 2: assistant. Total 3 messages.
    assert [m.role for m in messages] == [
        Role.ASSISTANT,
        Role.TOOL,
        Role.ASSISTANT,
    ]
    assert messages[0].tool_calls[0].name == "test_tool"
    assert messages[-1].content == "done"


async def test_stream_on_usage_called_from_final_chunk():
    """Usage rides the final chunk; on_usage fires once per streamed turn."""
    u = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    llm = _make_streaming_llm(
        [[StreamChunk(text="hi"), StreamChunk(usage=u)]]
    )
    agent = Agent(llm=llm, tools=[])
    context = Context()
    context.add(Message(role=Role.USER, content="hi"))

    collected: list[Usage] = []
    async for _item in agent.run(
        context, stream=True, on_usage=collected.append
    ):
        pass

    assert collected == [u]


# ---- session factories (create_session / load_session) ---------------------


class _CountingSource:
    """Context source whose output changes on every gather — lets tests
    distinguish a fresh rebuild from a restored snapshot."""

    def __init__(self):
        self.calls = 0

    @property
    def name(self) -> str:
        return "counter"

    async def gather(self, workspace_root) -> str:
        self.calls += 1
        return f"gathered {self.calls}"


def _make_factory_agent(workspace_root=None, model="test-model", **kwargs):
    llm = _make_llm(return_value=GenerateResponse(text="hi", tool_calls=None))
    llm.model = model
    llm.backend = "openai"
    return Agent(
        llm=llm,
        tools=[],
        prompt="you are a test agent",
        workspace_root=workspace_root,
        **kwargs,
    )


async def test_create_session_bakes_prompt_and_settings(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    agent = _make_factory_agent(workspace_root=ws)

    session = await agent.create_session(base_dir=tmp_path / "sessions")

    msgs = session.context.get_messages()
    assert msgs[0].role == Role.SYSTEM
    assert "you are a test agent" in msgs[0].content
    assert session.model == "test-model"
    assert session.backend == "openai"
    assert session.workspace_root == str(ws)


async def test_create_session_explicit_root_overrides(tmp_path):
    constructor_ws = tmp_path / "a"
    other_ws = tmp_path / "b"
    constructor_ws.mkdir()
    other_ws.mkdir()
    agent = _make_factory_agent(workspace_root=constructor_ws)

    session = await agent.create_session(
        other_ws, base_dir=tmp_path / "sessions"
    )
    assert session.workspace_root == str(other_ws)


async def test_create_session_without_any_root_raises(tmp_path):
    agent = _make_factory_agent(workspace_root=None)

    with pytest.raises(ValueError, match="workspace_root"):
        await agent.create_session(base_dir=tmp_path / "sessions")


async def test_load_session_reattaches_system_prompt(tmp_path):
    """Regression: resumed sessions must never run promptless."""
    ws = tmp_path / "ws"
    ws.mkdir()
    base = tmp_path / "sessions"
    agent = _make_factory_agent(workspace_root=ws)
    created = await agent.create_session(base_dir=base)

    loaded = await agent.load_session(created.session_id, base_dir=base)

    msgs = loaded.context.get_messages()
    assert msgs[0].role == Role.SYSTEM
    assert "you are a test agent" in msgs[0].content


async def test_load_session_rebuilds_prompt_fresh(tmp_path):
    """load_session rebuilds the prompt (rebuild, don't restore)."""
    ws = tmp_path / "ws"
    ws.mkdir()
    base = tmp_path / "sessions"
    source = _CountingSource()
    agent = _make_factory_agent(
        workspace_root=ws, context_sources=[source]
    )

    created = await agent.create_session(base_dir=base)
    assert "gathered 1" in created.context.get_messages()[0].content

    loaded = await agent.load_session(created.session_id, base_dir=base)
    assert "gathered 2" in loaded.context.get_messages()[0].content


async def test_load_session_rejects_different_model(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    base = tmp_path / "sessions"
    created = await _make_factory_agent(workspace_root=ws).create_session(
        base_dir=base
    )

    other = _make_factory_agent(workspace_root=ws, model="other-model")
    with pytest.raises(SessionConfigMismatchError, match="model"):
        await other.load_session(created.session_id, base_dir=base)


async def test_load_session_rejects_different_workspace(tmp_path):
    ws = tmp_path / "ws"
    other_ws = tmp_path / "other"
    ws.mkdir()
    other_ws.mkdir()
    base = tmp_path / "sessions"
    created = await _make_factory_agent(workspace_root=ws).create_session(
        base_dir=base
    )

    other = _make_factory_agent(workspace_root=other_ws)
    with pytest.raises(SessionConfigMismatchError, match="workspace"):
        await other.load_session(created.session_id, base_dir=base)


async def test_load_session_equal_roots_after_resolve_ok(tmp_path):
    """Different spellings of the same directory are not a mismatch."""
    ws = tmp_path / "ws"
    (ws / "sub").mkdir(parents=True)
    base = tmp_path / "sessions"
    created = await _make_factory_agent(workspace_root=ws).create_session(
        base_dir=base
    )

    same_ws_spelled_differently = ws / "sub" / ".."
    agent = _make_factory_agent(workspace_root=same_ws_spelled_differently)
    loaded = await agent.load_session(created.session_id, base_dir=base)
    assert loaded.session_id == created.session_id


async def test_load_session_legacy_meta_falls_back_to_agent_root(tmp_path):
    """Sessions persisted before workspace_root use the agent's root."""
    base = tmp_path / "sessions"
    legacy = Session.create(
        model="test-model", backend="openai", base_dir=base
    )  # no workspace_root persisted

    ws = tmp_path / "ws"
    ws.mkdir()
    agent = _make_factory_agent(workspace_root=ws)
    loaded = await agent.load_session(legacy.session_id, base_dir=base)
    assert loaded.context.get_messages()[0].role == Role.SYSTEM


async def test_load_session_no_root_anywhere_raises(tmp_path):
    base = tmp_path / "sessions"
    legacy = Session.create(
        model="test-model", backend="openai", base_dir=base
    )

    agent = _make_factory_agent(workspace_root=None)
    with pytest.raises(ValueError, match="workspace_root"):
        await agent.load_session(legacy.session_id, base_dir=base)
