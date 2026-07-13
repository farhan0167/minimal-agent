import json
from typing import AsyncIterator, List
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from minimal_agent.agent import Agent, Context, NullScope
from minimal_agent.agent.session import SessionConfigMismatchError, SessionManager
from minimal_agent.context_sources import (
    DirectoryTreeSource,
    GitStatusSource,
    Placement,
    WorkspaceSource,
    source_placement,
)
from minimal_agent.events import (
    EventEmitter,
    EventType,
    RunEnd,
    RunEndStatus,
    RunStart,
)
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
    llm = _make_llm(return_value=GenerateResponse(text="Hello!", tool_calls=None))
    agent = Agent(llm=llm, tools=[])
    context = Context(behavior_prompt="sys")
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


class _ImageTool(BaseTool[_EmptyInput, dict]):
    """Tool that returns an image part, like read_file on an image."""

    name = "image_tool"
    input_schema = _EmptyInput

    async def invoke(self, args: _EmptyInput, ctx: ToolContext) -> dict:
        return {"uri": "data:image/png;base64,ABC"}

    def render_result_for_assistant(self, out: dict) -> str:
        return "image attached below"

    def render_parts_for_assistant(self, out: dict):
        from minimal_agent.llm.types import ImagePart, ImageUrl

        return [ImagePart(image_url=ImageUrl(url=out["uri"]))]


async def test_image_tool_flushes_trailing_user_message():
    """A tool producing image parts yields a trailing USER message with the
    parts, positioned AFTER the tool result (API-legal ordering)."""
    responses = [
        GenerateResponse(
            text="reading",
            tool_calls=[ToolCall(id="tc_1", name="image_tool", arguments={})],
        ),
        GenerateResponse(text="I see it.", tool_calls=None),
    ]
    llm = _make_llm(side_effect=responses)
    agent = Agent(llm=llm, tools=[_ImageTool()])

    context = Context()
    context.add(Message(role=Role.USER, content="look"))

    messages = [msg async for msg in agent.run(context)]

    # assistant(tool_calls) → tool → user(parts) → assistant
    assert [m.role for m in messages] == [
        Role.ASSISTANT,
        Role.TOOL,
        Role.USER,
        Role.ASSISTANT,
    ]
    # The tool message is the text pointer (no image bytes on it).
    assert messages[1].content == "image attached below"
    # The trailing user message carries the image part.
    parts = messages[2].content
    assert isinstance(parts, list) and len(parts) == 1
    assert parts[0].image_url.url == "data:image/png;base64,ABC"


async def test_text_tool_produces_no_trailing_user_message():
    """A text-only tool contributes no parts — no synthetic user message."""
    responses = [
        GenerateResponse(
            text="checking",
            tool_calls=[ToolCall(id="tc_1", name="test_tool", arguments={})],
        ),
        GenerateResponse(text="done", tool_calls=None),
    ]
    llm = _make_llm(side_effect=responses)
    agent = Agent(llm=llm, tools=[_make_tool("test_tool")])

    context = Context()
    context.add(Message(role=Role.USER, content="go"))

    messages = [msg async for msg in agent.run(context)]

    assert [m.role for m in messages] == [Role.ASSISTANT, Role.TOOL, Role.ASSISTANT]


async def test_context_store_matches_yielded():
    """After run(), the context store contains exactly the yielded messages
    plus the original user message."""
    llm = _make_llm(return_value=GenerateResponse(text="done", tool_calls=None))
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
            tool_calls=[ToolCall(id="tc_1", name="test_tool", arguments={})],
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
    async for _msg in agent.run(context, on_usage=collected.append):
        pass

    assert len(collected) == 2
    assert collected[0] == u1
    assert collected[1] == u2


async def test_on_usage_not_called_when_none():
    """on_usage is not called if resp.usage is None."""
    llm = _make_llm(
        return_value=GenerateResponse(text="hi", tool_calls=None, usage=None)
    )
    agent = Agent(llm=llm, tools=[])

    context = Context()
    context.add(Message(role=Role.USER, content="hi"))

    collected: list[Usage] = []
    async for _msg in agent.run(context, on_usage=collected.append):
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
    llm = _make_streaming_llm([[StreamChunk(text="Hel"), StreamChunk(text="lo!")]])
    agent = Agent(llm=llm, tools=[])
    context = Context(behavior_prompt="sys")
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
        StreamChunk(tool_calls=[ToolCallDelta(index=0, id="tc_1", name="test_tool")]),
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
    llm = _make_streaming_llm([[StreamChunk(text="hi"), StreamChunk(usage=u)]])
    agent = Agent(llm=llm, tools=[])
    context = Context()
    context.add(Message(role=Role.USER, content="hi"))

    collected: list[Usage] = []
    async for _item in agent.run(context, stream=True, on_usage=collected.append):
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

    async def gather(self, env) -> str:
        self.calls += 1
        return f"gathered {self.calls}"


def _make_factory_agent(
    workspace_root=None, model="test-model", base_dir=None, **kwargs
):
    llm = _make_llm(return_value=GenerateResponse(text="hi", tool_calls=None))
    llm.model = model
    llm.backend = "openai"
    if base_dir is not None:
        kwargs["session_manager"] = SessionManager(base_dir=base_dir)
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
    agent = _make_factory_agent(workspace_root=ws, base_dir=tmp_path / "sessions")

    session = await agent.create_session()

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
    agent = _make_factory_agent(
        workspace_root=constructor_ws, base_dir=tmp_path / "sessions"
    )

    session = await agent.create_session(other_ws)
    assert session.workspace_root == str(other_ws)


async def test_create_session_without_any_root_raises(tmp_path):
    agent = _make_factory_agent(workspace_root=None, base_dir=tmp_path / "sessions")

    with pytest.raises(ValueError, match="workspace_root"):
        await agent.create_session()


async def test_load_session_reattaches_system_prompt(tmp_path):
    """Regression: resumed sessions must never run promptless."""
    ws = tmp_path / "ws"
    ws.mkdir()
    base = tmp_path / "sessions"
    agent = _make_factory_agent(workspace_root=ws, base_dir=base)
    created = await agent.create_session()

    loaded = await agent.load_session(created.session_id)

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
        workspace_root=ws, context_sources=[source], base_dir=base
    )

    created = await agent.create_session()
    await created.context.ensure_session_gathered()
    assert "gathered 1" in created.context.get_messages()[0].content

    loaded = await agent.load_session(created.session_id)
    await loaded.context.ensure_session_gathered()
    assert "gathered 2" in loaded.context.get_messages()[0].content


async def test_load_session_rejects_different_model(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    base = tmp_path / "sessions"
    created = await _make_factory_agent(
        workspace_root=ws, base_dir=base
    ).create_session()

    other = _make_factory_agent(workspace_root=ws, model="other-model", base_dir=base)
    with pytest.raises(SessionConfigMismatchError, match="model"):
        await other.load_session(created.session_id)


async def test_load_session_rejects_different_workspace(tmp_path):
    ws = tmp_path / "ws"
    other_ws = tmp_path / "other"
    ws.mkdir()
    other_ws.mkdir()
    base = tmp_path / "sessions"
    created = await _make_factory_agent(
        workspace_root=ws, base_dir=base
    ).create_session()

    other = _make_factory_agent(workspace_root=other_ws, base_dir=base)
    with pytest.raises(SessionConfigMismatchError, match="workspace"):
        await other.load_session(created.session_id)


async def test_load_session_equal_roots_after_resolve_ok(tmp_path):
    """Different spellings of the same directory are not a mismatch."""
    ws = tmp_path / "ws"
    (ws / "sub").mkdir(parents=True)
    base = tmp_path / "sessions"
    created = await _make_factory_agent(
        workspace_root=ws, base_dir=base
    ).create_session()

    same_ws_spelled_differently = ws / "sub" / ".."
    agent = _make_factory_agent(
        workspace_root=same_ws_spelled_differently, base_dir=base
    )
    loaded = await agent.load_session(created.session_id)
    assert loaded.session_id == created.session_id


async def test_load_session_legacy_meta_falls_back_to_agent_root(tmp_path):
    """Sessions persisted before workspace_root use the agent's root."""
    base = tmp_path / "sessions"
    legacy = SessionManager(base_dir=base).create_session(
        model="test-model", backend="openai"
    )  # no workspace_root persisted

    ws = tmp_path / "ws"
    ws.mkdir()
    agent = _make_factory_agent(workspace_root=ws, base_dir=base)
    loaded = await agent.load_session(legacy.session_id)
    assert loaded.context.get_messages()[0].role == Role.SYSTEM


async def test_load_session_no_root_anywhere_raises(tmp_path):
    base = tmp_path / "sessions"
    legacy = SessionManager(base_dir=base).create_session(
        model="test-model", backend="openai"
    )

    agent = _make_factory_agent(workspace_root=None, base_dir=base)
    with pytest.raises(ValueError, match="workspace_root"):
        await agent.load_session(legacy.session_id)


# ---- live sources through the loop (Placement.RUN / Placement.CALL) --------


class _CountingLiveSource:
    """Live source whose content carries the gather count."""

    def __init__(self, name: str, placement: Placement):
        self.name = name
        self.placement = placement
        self.calls = 0

    async def gather(self, env) -> str:
        self.calls += 1
        return f"live gather {self.calls}"


def _sent_messages(llm) -> list[list[Message]]:
    """The messages= list of every llm.generate() call, in order."""
    return [c.kwargs["messages"] for c in llm.generate.call_args_list]


def _user_texts(msgs: list[Message]) -> list[str]:
    return [m.content for m in msgs if m.role is Role.USER]


async def _session_with_source(tmp_path, source, llm_responses):
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    llm = _make_llm(side_effect=llm_responses)
    llm.model = "test-model"
    llm.backend = "openai"
    agent = Agent(
        llm=llm,
        tools=[_make_tool("test_tool")],
        prompt="you are a test agent",
        context_sources=[source],
        workspace_root=ws,
        session_manager=SessionManager(base_dir=tmp_path / "sessions"),
    )
    session = await agent.create_session()
    return agent, session, llm


async def test_run_source_merged_into_user_message_and_stable(tmp_path):
    source = _CountingLiveSource("probe", Placement.RUN)
    agent, session, llm = await _session_with_source(
        tmp_path,
        source,
        [
            GenerateResponse(
                text="checking",
                tool_calls=[ToolCall(id="tc_1", name="test_tool", arguments={})],
            ),
            GenerateResponse(text="done", tool_calls=None),
        ],
    )
    session.context.add(Message(role=Role.USER, content="what changed?"))

    async for _ in agent.run(session.context):
        pass

    sent = _sent_messages(llm)
    assert len(sent) == 2
    first_user = _user_texts(sent[0])[-1]
    assert first_user.startswith("what changed?")
    assert '<context name="probe">' in first_user
    assert "live gather 1" in first_user
    # Gathered once for the run, byte-identical on the second call.
    assert source.calls == 1
    assert _user_texts(sent[1])[-1] == first_user
    # The system prompt never carries a RUN source.
    assert "probe" not in sent[0][0].content
    # The store keeps the clean user message.
    assert session.context.store.messages[0].content == "what changed?"


async def test_second_run_regathers_run_source(tmp_path):
    source = _CountingLiveSource("probe", Placement.RUN)
    agent, session, llm = await _session_with_source(
        tmp_path,
        source,
        [
            GenerateResponse(text="hi", tool_calls=None),
            GenerateResponse(text="hi again", tool_calls=None),
        ],
    )

    session.context.add(Message(role=Role.USER, content="run one"))
    async for _ in agent.run(session.context):
        pass
    session.context.add(Message(role=Role.USER, content="run two"))
    async for _ in agent.run(session.context):
        pass

    assert source.calls == 2
    second_user = _user_texts(_sent_messages(llm)[1])[-1]
    assert second_user.startswith("run two")
    assert "live gather 2" in second_user


async def test_call_source_gathered_every_llm_call(tmp_path):
    source = _CountingLiveSource("watcher", Placement.CALL)
    agent, session, llm = await _session_with_source(
        tmp_path,
        source,
        [
            GenerateResponse(
                text="checking",
                tool_calls=[ToolCall(id="tc_1", name="test_tool", arguments={})],
            ),
            GenerateResponse(text="done", tool_calls=None),
        ],
    )
    session.context.add(Message(role=Role.USER, content="go"))

    async for _ in agent.run(session.context):
        pass

    assert source.calls == 2
    sent = _sent_messages(llm)
    # Call 1: merged into the trailing user message.
    assert "live gather 1" in _user_texts(sent[0])[-1]
    # Call 2: standalone carrier after the tool result.
    assert sent[1][-1].role is Role.USER
    assert "live gather 2" in sent[1][-1].content
    assert sent[1][-2].role is Role.TOOL


async def test_streaming_run_assembles_like_nonstreaming(tmp_path):
    source = _CountingLiveSource("probe", Placement.RUN)
    ws = tmp_path / "ws"
    ws.mkdir()

    captured: list[list[Message]] = []

    async def _gen():
        yield StreamChunk(text="hi")

    def _stream(**kwargs):
        captured.append(kwargs["messages"])
        return _gen()

    llm = AsyncMock()
    llm.stream = _stream
    llm.model = "test-model"
    llm.backend = "openai"
    agent = Agent(
        llm=llm,
        tools=[],
        prompt="you are a test agent",
        context_sources=[source],
        workspace_root=ws,
        session_manager=SessionManager(base_dir=tmp_path / "sessions"),
    )
    session = await agent.create_session()
    session.context.add(Message(role=Role.USER, content="hello"))

    async for _ in agent.run(session.context, stream=True):
        pass

    assert len(captured) == 1
    user = _user_texts(captured[0])[-1]
    assert user.startswith("hello")
    assert "live gather 1" in user


async def test_factories_partition_session_and_live_sources(tmp_path):
    run_src = _CountingLiveSource("liveProbe", Placement.RUN)
    session_src = _CountingSource()  # bare → SESSION
    ws = tmp_path / "ws"
    ws.mkdir()
    base = tmp_path / "sessions"
    agent = _make_factory_agent(
        workspace_root=ws, context_sources=[session_src, run_src], base_dir=base
    )

    created = await agent.create_session()
    await created.context.ensure_session_gathered()
    prompt = created.context.get_messages()[0].content
    assert "gathered 1" in prompt  # SESSION source in the rendered prompt
    assert "liveProbe" not in prompt  # RUN source stays out

    created.context.add(Message(role=Role.USER, content="hi"))
    msgs = await created.context.assemble()
    assert '<context name="liveProbe">' in msgs[-1].content

    # load_session re-attaches the live sources too.
    loaded = await agent.load_session(created.session_id)
    loaded.context.add(Message(role=Role.USER, content="again"))
    msgs = await loaded.context.assemble()
    assert '<context name="liveProbe">' in msgs[-1].content


def test_default_prompt_puts_git_status_on_message_channel():
    def _by_placement(agent, placement):
        return [s for s in agent.context_sources if source_placement(s) is placement]

    # Custom prompt → no default git/tree sources, but AGENTS.md rides
    # alongside every agent (RUN-placed), so it's the sole live source.
    agent = _make_factory_agent()
    live = [
        s for s in agent.context_sources if source_placement(s) is not Placement.SESSION
    ]
    assert [type(s).__name__ for s in live] == ["AgentsMdSource"]
    # WorkspaceSource rides every identity, first in line.
    assert isinstance(agent.context_sources[0], WorkspaceSource)

    llm = _make_llm(return_value=GenerateResponse(text="hi", tool_calls=None))
    llm.model = "test-model"
    llm.backend = "openai"
    default_agent = Agent(llm=llm, tools=[])  # default prompt
    run_sources = _by_placement(default_agent, Placement.RUN)
    session_sources = _by_placement(default_agent, Placement.SESSION)
    assert any(isinstance(s, GitStatusSource) for s in run_sources)
    assert all(not isinstance(s, GitStatusSource) for s in session_sources)
    assert any(isinstance(s, DirectoryTreeSource) for s in session_sources)


async def test_default_agent_injects_git_status_into_user_message(tmp_path):
    """End to end in a real git repo: git status rides the merged user
    message, not the system prompt."""
    import asyncio

    ws = tmp_path / "ws"
    ws.mkdir()

    async def _git(*args):
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(ws),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    await _git("init")
    await _git("config", "user.email", "t@t.com")
    await _git("config", "user.name", "T")
    (ws / "f.txt").write_text("x")
    await _git("add", ".")
    await _git("commit", "-m", "init")

    llm = _make_llm(return_value=GenerateResponse(text="hi", tool_calls=None))
    llm.model = "test-model"
    llm.backend = "openai"
    agent = Agent(
        llm=llm,
        tools=[],
        workspace_root=ws,
        session_manager=SessionManager(base_dir=tmp_path / "sessions"),
    )
    session = await agent.create_session()

    session.context.add(Message(role=Role.USER, content="status?"))
    async for _ in agent.run(session.context):
        pass

    # The gathered (post-run) system prompt never carries a RUN source.
    assert '<context name="gitStatus">' not in session.context.system_prompt

    sent_user = _user_texts(_sent_messages(llm)[0])[-1]
    assert '<context name="gitStatus">' in sent_user
    assert "Branch:" in sent_user


# ---- observability (run.start / call.response / run.end) -------------------


class _RecorderSink:
    def __init__(self):
        self.envelopes = []

    def handle(self, env) -> None:
        self.envelopes.append(env)


def _recorded_context(**ctx_kwargs) -> tuple[Context, "_RecorderSink"]:
    rec = _RecorderSink()
    scope = NullScope()
    scope.events = EventEmitter(sinks=[rec])
    ctx = Context(scope=scope, **ctx_kwargs)
    return ctx, rec


def _event_types(rec: "_RecorderSink") -> list[str]:
    return [env.event.type for env in rec.envelopes]


def _traced_llm(responses) -> AsyncMock:
    llm = _make_llm(side_effect=responses)
    llm.model = "test-model"
    llm.backend = "openai"
    return llm


async def test_two_call_run_emits_ordered_events_sharing_one_run_id():
    u = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    llm = _traced_llm(
        [
            GenerateResponse(
                text="checking",
                tool_calls=[ToolCall(id="tc_1", name="test_tool", arguments={})],
                usage=u,
            ),
            GenerateResponse(text="done", tool_calls=None),
        ]
    )
    agent = Agent(llm=llm, tools=[_make_tool("test_tool")])
    context, rec = _recorded_context()
    context.add(Message(role=Role.USER, content="go"))

    async for _ in agent.run(context):
        pass

    assert _event_types(rec) == [
        EventType.RUN_START,
        EventType.CALL_REQUEST,
        EventType.CALL_RESPONSE,
        EventType.TOOL_START,
        EventType.TOOL_END,
        EventType.CALL_REQUEST,
        EventType.CALL_RESPONSE,
        EventType.RUN_END,
    ]
    run_ids = {env.run_id for env in rec.envelopes}
    assert len(run_ids) == 1 and run_ids != {None}

    first_response = rec.envelopes[2].event
    assert first_response.usage == u.model_dump()
    assert first_response.tool_calls == 1
    end = rec.envelopes[-1].event
    assert end.status is RunEndStatus.COMPLETED
    assert end.calls == 2


async def test_second_run_gets_a_distinct_run_id():
    llm = _traced_llm(
        [
            GenerateResponse(text="one", tool_calls=None),
            GenerateResponse(text="two", tool_calls=None),
        ]
    )
    agent = Agent(llm=llm, tools=[])
    context, rec = _recorded_context()

    context.add(Message(role=Role.USER, content="a"))
    async for _ in agent.run(context):
        pass
    context.add(Message(role=Role.USER, content="b"))
    async for _ in agent.run(context):
        pass

    starts = [env.run_id for env in rec.envelopes if isinstance(env.event, RunStart)]
    assert len(starts) == 2
    assert starts[0] != starts[1]


async def test_max_turns_exhaustion_records_max_turns_status():
    llm = _traced_llm(
        [
            GenerateResponse(
                text="again",
                tool_calls=[ToolCall(id=f"tc_{i}", name="test_tool", arguments={})],
            )
            for i in range(2)
        ]
    )
    agent = Agent(llm=llm, tools=[_make_tool("test_tool")], max_turns=2)
    context, rec = _recorded_context()
    context.add(Message(role=Role.USER, content="go"))

    async for _ in agent.run(context):
        pass

    end = next(env.event for env in rec.envelopes if isinstance(env.event, RunEnd))
    assert end.status is RunEndStatus.MAX_TURNS
    assert end.calls == 2


async def test_closing_generator_mid_run_records_abandoned():
    llm = _traced_llm(
        [
            GenerateResponse(
                text="checking",
                tool_calls=[ToolCall(id="tc_1", name="test_tool", arguments={})],
            ),
            GenerateResponse(text="never reached", tool_calls=None),
        ]
    )
    agent = Agent(llm=llm, tools=[_make_tool("test_tool")])
    context, rec = _recorded_context()
    context.add(Message(role=Role.USER, content="go"))

    gen = agent.run(context)
    await gen.__anext__()  # assistant message with a pending tool call
    await gen.aclose()  # consumer disconnects

    end = next(env.event for env in rec.envelopes if isinstance(env.event, RunEnd))
    assert end.status is RunEndStatus.ABANDONED


async def test_llm_exception_records_error_and_still_propagates():
    llm = _make_llm(side_effect=RuntimeError("api down"))
    llm.model = "test-model"
    llm.backend = "openai"
    agent = Agent(llm=llm, tools=[])
    context, rec = _recorded_context()
    context.add(Message(role=Role.USER, content="go"))

    with pytest.raises(RuntimeError, match="api down"):
        async for _ in agent.run(context):
            pass

    end = next(env.event for env in rec.envelopes if isinstance(env.event, RunEnd))
    assert end.status is RunEndStatus.ERROR


async def test_streaming_and_nonstreaming_emit_equivalent_sequences():
    streaming_llm = _make_streaming_llm([[StreamChunk(text="hi")]])
    streaming_llm.model = "test-model"
    streaming_llm.backend = "openai"
    stream_ctx, stream_rec = _recorded_context()
    stream_ctx.add(Message(role=Role.USER, content="go"))
    async for _ in Agent(llm=streaming_llm, tools=[]).run(stream_ctx, stream=True):
        pass

    plain_llm = _traced_llm([GenerateResponse(text="hi", tool_calls=None)])
    plain_ctx, plain_rec = _recorded_context()
    plain_ctx.add(Message(role=Role.USER, content="go"))
    async for _ in Agent(llm=plain_llm, tools=[]).run(plain_ctx):
        pass

    assert _event_types(stream_rec) == _event_types(plain_rec)


async def test_run_start_tools_json_parses_back_to_the_tool_schemas():
    llm = _traced_llm([GenerateResponse(text="hi", tool_calls=None)])
    agent = Agent(llm=llm, tools=[_make_tool("test_tool")])
    context, rec = _recorded_context()
    context.add(Message(role=Role.USER, content="go"))

    async for _ in agent.run(context):
        pass

    start = next(env.event for env in rec.envelopes if isinstance(env.event, RunStart))
    assert start.model == "test-model"
    assert start.backend == "openai"
    parsed = json.loads(start.tools_json)
    assert [t["name"] for t in parsed] == ["test_tool"]
    assert parsed == [t.model_dump() for t in agent._llm_tools]


async def test_bare_context_emits_nothing_and_runs_unchanged():
    llm = _make_llm(return_value=GenerateResponse(text="hi", tool_calls=None))
    agent = Agent(llm=llm, tools=[])
    context = Context()  # NullScope: zero-sink emitter
    context.add(Message(role=Role.USER, content="go"))

    messages = [msg async for msg in agent.run(context)]

    assert len(messages) == 1  # no events machinery in the way


async def test_run_start_carries_fully_rendered_prompt():
    """run.start must record the prompt the run's calls will see: the
    SESSION gather happens before the event is emitted (run 1), and the
    cached snapshot keeps later runs identical."""
    from pathlib import Path

    llm = _traced_llm(
        [
            GenerateResponse(text="one", tool_calls=None),
            GenerateResponse(text="two", tool_calls=None),
        ]
    )
    agent = Agent(llm=llm, tools=[])
    context, rec = _recorded_context(
        behavior_prompt="sys",
        context_sources=[_CountingSource()],
        workspace_root=Path("ws"),
    )

    context.add(Message(role=Role.USER, content="go"))
    async for _ in agent.run(context):
        pass
    context.add(Message(role=Role.USER, content="more"))
    async for _ in agent.run(context):
        pass

    starts = [env.event for env in rec.envelopes if isinstance(env.event, RunStart)]
    assert len(starts) == 2
    assert starts[0].system_prompt.startswith("sys")
    assert "gathered 1" in starts[0].system_prompt  # rendered, not bare
    # Run 2 re-emits the same snapshot — gathered once per context.
    assert starts[1].system_prompt == starts[0].system_prompt
    assert starts[0].system_prompt == context.system_prompt


# ---- load_prompt (identity resolution, relocated from the deleted builder) --


class TestLoadPrompt:
    def test_none_loads_default(self):
        from minimal_agent.agent.agent import load_prompt

        result = load_prompt(None)
        assert "software engineering" in result.lower() or "tool" in result.lower()
        assert len(result) > 50

    def test_string_returns_as_is(self):
        from minimal_agent.agent.agent import load_prompt

        assert load_prompt("You are a test agent.") == "You are a test agent."

    def test_path_reads_file(self, tmp_path):
        from pathlib import Path

        from minimal_agent.agent.agent import load_prompt

        prompt_file = tmp_path / "my_prompt.md"
        prompt_file.write_text("Custom prompt content.")
        assert load_prompt(Path(prompt_file)) == "Custom prompt content."


# ---- pluggable Context class (context_cls) ---------------------------------


class _LastTwoContext(Context):
    """Projection strategy: the LLM sees only the last two messages."""

    def project(self) -> List[Message]:
        return self._store.messages[-2:]


def test_context_cls_defaults_to_context():
    agent = Agent(llm=_make_llm(), tools=[])
    assert agent.context_cls is Context


def test_context_cls_is_identity():
    agent = Agent(llm=_make_llm(), tools=[], context_cls=_LastTwoContext)
    assert agent.context_cls is _LastTwoContext


async def test_create_session_builds_the_agents_context_class(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    agent = _make_factory_agent(
        workspace_root=ws, base_dir=tmp_path / "sessions", context_cls=_LastTwoContext
    )

    session = await agent.create_session()

    assert isinstance(session.context, _LastTwoContext)


async def test_load_session_rebuilds_the_same_context_class(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    base = tmp_path / "sessions"
    agent = _make_factory_agent(
        workspace_root=ws, base_dir=base, context_cls=_LastTwoContext
    )
    created = await agent.create_session()

    loaded = await agent.load_session(created.session_id)

    assert isinstance(loaded.context, _LastTwoContext)


async def test_load_session_rejects_swapped_context_class(tmp_path):
    """A windowed session resumed under the plain Context would silently ship
    the whole transcript — the exact drift the check exists to catch."""
    ws = tmp_path / "ws"
    ws.mkdir()
    base = tmp_path / "sessions"
    created = await _make_factory_agent(
        workspace_root=ws, base_dir=base, context_cls=_LastTwoContext
    ).create_session()

    plain = _make_factory_agent(workspace_root=ws, base_dir=base)
    with pytest.raises(SessionConfigMismatchError) as exc:
        await plain.load_session(created.session_id)

    msg = str(exc.value)
    assert "context_cls" in msg
    assert "_LastTwoContext" in msg  # the persisted side
    assert "minimal_agent.agent.context.Context" in msg  # the current side


async def test_load_session_rejects_context_class_added_to_default_session(tmp_path):
    """The reverse drift: full → windowed silently truncates live history."""
    ws = tmp_path / "ws"
    ws.mkdir()
    base = tmp_path / "sessions"
    created = await _make_factory_agent(
        workspace_root=ws, base_dir=base
    ).create_session()

    windowed = _make_factory_agent(
        workspace_root=ws, base_dir=base, context_cls=_LastTwoContext
    )
    with pytest.raises(SessionConfigMismatchError, match="context_cls"):
        await windowed.load_session(created.session_id)


async def test_projection_shapes_what_the_llm_sees_without_touching_the_store():
    """End-to-end: the subclass's project() governs the LLM input, and the
    store still holds the whole durable transcript (invariant 7)."""
    llm = _make_llm(return_value=GenerateResponse(text="ok", tool_calls=None))
    agent = Agent(llm=llm, tools=[], context_cls=_LastTwoContext)

    context = agent.context_cls(behavior_prompt="sys")
    for i in range(5):
        context.add(Message(role=Role.USER, content=f"m{i}"))

    [msg async for msg in agent.run(context)]

    sent = llm.generate.call_args.kwargs["messages"]
    non_system = [m for m in sent if m.role is not Role.SYSTEM]
    assert [m.content for m in non_system] == ["m3", "m4"]
    # The store is the durable transcript — projection is only a view of it.
    assert [m.content for m in context.store.messages if m.role is Role.USER] == [
        "m0",
        "m1",
        "m2",
        "m3",
        "m4",
    ]
