"""Tests for the audit reader: on-demand reconstruction from a session dir."""

from typing import ClassVar
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from minimal_agent.agent import Agent
from minimal_agent.agent.session import SessionManager
from minimal_agent.audit import (
    CallRecordNotFoundError,
    read_call_records,
    read_events,
    reconstruct_call,
    session_runs,
)
from minimal_agent.context_sources import Placement
from minimal_agent.events import RunEnd, RunEndStatus, RunStart
from minimal_agent.llm.types import (
    GenerateResponse,
    Message,
    Role,
    ToolCall,
    Usage,
)
from minimal_agent.tools.base import BaseTool
from minimal_agent.tools.context import ToolContext


class _RunSource:
    name = "probe"
    placement = Placement.RUN

    async def gather(self, workspace_root) -> str:
        return "fresh data"


async def _session_with_one_call(tmp_path, **create_overrides):
    """A session with one recorded call, framed by a real run (run.start emits
    the fingerprint that reconstruction joins to)."""
    defaults = dict(
        model="test-model",
        backend="openai",
        system_prompt="you are helpful",
    )
    defaults.update(create_overrides)
    session = SessionManager(base_dir=tmp_path).create_session(**defaults)
    events = session.context.events
    events.emit(
        RunStart(
            model=defaults["model"],
            backend=defaults["backend"],
            tools_json="[]",
            system_prompt=defaults["system_prompt"],
            store_len=len(session.context.store),
        )
    )
    session.context.add(Message(role=Role.USER, content="what changed?"))
    assembled = await session.context.assemble()
    events.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=1))
    return session, assembled


async def test_reconstruct_call_matches_assembled_output(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    session, assembled = await _session_with_one_call(
        tmp_path, workspace_root=str(ws), live_sources=[_RunSource()]
    )

    (record,) = read_call_records(session.session_dir)
    result = reconstruct_call(session.session_dir, record["call_id"])

    assert result.messages == assembled
    assert result.verified
    assert result.computed_sha256 == result.recorded_sha256
    # Fingerprint joins from the run record (written at run.start).
    assert result.model == "test-model"
    assert result.tools == []


async def test_reconstruct_call_without_injection(tmp_path):
    session, assembled = await _session_with_one_call(tmp_path)

    (record,) = read_call_records(session.session_dir)
    result = reconstruct_call(session.session_dir, record["call_id"])

    assert result.messages == assembled
    assert result.verified
    assert result.messages[0].role is Role.SYSTEM
    assert result.messages[0].content == "you are helpful"


async def test_reconstruct_unknown_call_id_raises(tmp_path):
    session, _ = await _session_with_one_call(tmp_path)

    with pytest.raises(CallRecordNotFoundError, match="nope"):
        reconstruct_call(session.session_dir, "nope")


async def test_tampered_transcript_reports_unverified_not_error(tmp_path):
    session, _ = await _session_with_one_call(tmp_path)
    messages_path = session.session_dir / "messages.jsonl"
    tampered = Message(role=Role.USER, content="something else entirely")
    messages_path.write_text(tampered.model_dump_json() + "\n")

    (record,) = read_call_records(session.session_dir)
    result = reconstruct_call(session.session_dir, record["call_id"])

    assert not result.verified
    assert result.computed_sha256 != result.recorded_sha256


def test_readers_return_empty_for_sessions_predating_the_artifacts(tmp_path):
    session = SessionManager(base_dir=tmp_path).create_session(
        model="test-model", backend="openai"
    )
    (session.session_dir / "events.jsonl").unlink()

    assert read_events(session.session_dir) == []
    assert read_call_records(session.session_dir) == []


async def test_read_events_returns_timeline_in_order(tmp_path):
    session, _ = await _session_with_one_call(tmp_path)

    events = read_events(session.session_dir)

    assert [e["type"] for e in events] == [
        "session.created",
        "run.start",
        "call.request",
        "run.end",
    ]


# ---- session_runs (the holistic view) ---------------------------------------


class _EmptyInput(BaseModel):
    pass


class _EchoTool(BaseTool[_EmptyInput, str]):
    name: ClassVar[str] = "probe_tool"
    input_schema: ClassVar[type[BaseModel]] = _EmptyInput

    async def invoke(self, args: _EmptyInput, ctx: ToolContext) -> str:
        return "probe result"


async def _run_two_call_session(tmp_path):
    """A real Agent.run against a persisted session: tool round + answer."""
    ws = tmp_path / "ws"
    ws.mkdir()
    llm = AsyncMock()
    llm.model = "test-model"
    llm.backend = "openai"
    llm.generate = AsyncMock(
        side_effect=[
            GenerateResponse(
                text="checking",
                tool_calls=[ToolCall(id="tc_1", name="probe_tool", arguments={})],
                usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            ),
            GenerateResponse(text="the answer", tool_calls=None),
        ]
    )
    agent = Agent(
        llm=llm,
        tools=[_EchoTool()],
        prompt="you are a test agent",
        workspace_root=ws,
        enable_skills=False,
        sessions=SessionManager(base_dir=tmp_path / "sessions"),
    )
    session = await agent.create_session()
    session.context.add(Message(role=Role.USER, content="go"))
    async for _ in agent.run(session.context):
        pass
    return session


async def test_session_runs_joins_everything(tmp_path):
    session = await _run_two_call_session(tmp_path)

    (run,) = session_runs(session.session_dir)

    assert run.model == "test-model"
    assert run.backend == "openai"
    assert run.status == "completed"
    assert run.started_at is not None
    assert run.duration_ms is not None
    assert len(run.calls) == 2

    first, second = run.calls
    # Full input inline, verified against the recorded hash.
    assert first.input.verified and second.input.verified
    assert first.input.messages[0].role is Role.SYSTEM
    # The response is the message at store index store_len.
    assert first.response.role is Role.ASSISTANT
    assert first.response.tool_calls[0].name == "probe_tool"
    assert second.response.content == "the answer"
    # call.response metadata joined in.
    assert first.latency_ms is not None
    assert first.usage == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }
    # The tool round rides the first call.
    (execution,) = first.tool_executions
    assert execution.name == "probe_tool"
    assert execution.status == "ok"
    assert second.tool_executions == []
    # Inputs grow monotonically — call 2 saw call 1's reply and tool result.
    assert len(second.input.messages) > len(first.input.messages)


async def test_session_runs_degraded_direct_assemble(tmp_path):
    # A host calling assemble() directly, with no run.start ever emitted.
    session = SessionManager(base_dir=tmp_path).create_session(
        model="test-model", backend="openai", system_prompt="you are helpful"
    )
    session.context.add(Message(role=Role.USER, content="what changed?"))
    await session.context.assemble()

    (run,) = session_runs(session.session_dir)

    # No run row exists: frame metadata is null, and reconstruction can't
    # recover the system prompt — the call is unverified but still surfaced.
    assert run.started_at is None
    assert run.status is None
    (call,) = run.calls
    assert not call.input.verified
    assert call.input.unverified_reason is not None
    assert call.response is None  # no reply was ever stored
    assert call.latency_ms is None


def test_session_runs_empty_session(tmp_path):
    session = SessionManager(base_dir=tmp_path).create_session(
        model="test-model", backend="openai"
    )
    assert session_runs(session.session_dir) == []


async def test_reconstruct_carries_fingerprint_and_parsed_tools(tmp_path):
    session = SessionManager(base_dir=tmp_path).create_session(
        model="test-model", backend="openai"
    )
    session.context.events.emit(
        RunStart(
            model="test-model",
            backend="openai",
            tools_json='[{"name":"echo"}]',
            system_prompt=None,
            store_len=0,
        )
    )
    session.context.add(Message(role=Role.USER, content="hi"))
    await session.context.assemble()

    (record,) = read_call_records(session.session_dir)
    result = reconstruct_call(session.session_dir, record["call_id"])

    assert result.verified
    assert result.model == "test-model"
    assert result.backend == "openai"
    assert result.tools == [{"name": "echo"}]


# ---- the recording tree (child scopes, spawned agents) -----------------------


async def test_reconstruct_call_in_child_scope_resolves_root_blobs(tmp_path):
    """Children share the session root's blobs/ — reconstruction walks up."""
    session = SessionManager(base_dir=tmp_path).create_session(
        model="test-model", backend="openai", system_prompt="root sys"
    )

    with session.scope.child(spawned_by="t", task="x") as child:
        ctx = child.new_context(system_prompt="child sys")
        child.events.emit(
            RunStart(
                model="test-model",
                backend="openai",
                tools_json="[]",
                system_prompt=ctx.system_prompt,
                store_len=len(ctx.store),
            )
        )
        ctx.add(Message(role=Role.USER, content="hi"))
        assembled = await ctx.assemble()
        child.events.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=1))

    assert not (child.dir / "blobs").exists()  # kit has no local blob store
    (record,) = read_call_records(child.dir)
    result = reconstruct_call(child.dir, record["call_id"])
    assert result.verified
    assert result.messages == assembled
    assert result.messages[0].content == "child sys"


async def test_session_runs_surfaces_spawned_agents(tmp_path):
    session = SessionManager(base_dir=tmp_path).create_session(
        model="test-model", backend="openai", system_prompt="sys"
    )
    scope = session.scope
    scope.events.emit(
        RunStart(
            model="test-model",
            backend="openai",
            tools_json="[]",
            system_prompt=None,
            store_len=0,
        )
    )
    session.context.add(Message(role=Role.USER, content="go"))
    await session.context.assemble()  # call c1

    with scope.child(spawned_by="spawn_agents", task="sub task", tool_call_id="tc_1"):
        pass

    (run,) = session_runs(session.session_dir)
    (call,) = run.calls
    (agent,) = call.spawned_agents
    assert agent.spawned_by == "spawn_agents"
    assert agent.task == "sub task"
    assert agent.tool_call_id == "tc_1"
    assert agent.status == "completed"  # joined from agent.end


async def test_tool_end_children_surface_in_tool_executions(tmp_path):
    from minimal_agent.events import ToolEnd, ToolStart

    session = SessionManager(base_dir=tmp_path).create_session(
        model="test-model", backend="openai", system_prompt="sys"
    )
    scope = session.scope
    scope.events.emit(
        RunStart(
            model="test-model",
            backend="openai",
            tools_json="[]",
            system_prompt=None,
            store_len=0,
        )
    )
    session.context.add(Message(role=Role.USER, content="go"))
    await session.context.assemble()
    scope.events.emit(ToolStart(tool_call_id="tc_1", name="spawner"))
    scope.events.emit(
        ToolEnd(
            tool_call_id="tc_1",
            name="spawner",
            status="ok",
            duration_ms=5,
            children=("a-11112222",),
        )
    )

    (run,) = session_runs(session.session_dir)
    (execution,) = run.calls[0].tool_executions
    assert execution.children == ["a-11112222"]


async def test_session_tree_walks_nested_agents(tmp_path):
    from minimal_agent.audit import session_tree

    session = SessionManager(base_dir=tmp_path).create_session(
        model="test-model", backend="openai", system_prompt="root sys"
    )

    with session.scope.child(spawned_by="t", task="inner work") as child:
        ctx = child.new_context(system_prompt="child sys")
        child.events.emit(
            RunStart(
                model="test-model",
                backend="openai",
                tools_json="[]",
                system_prompt=ctx.system_prompt,
                store_len=len(ctx.store),
            )
        )
        ctx.add(Message(role=Role.USER, content="hi"))
        await ctx.assemble()
        child.events.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=1))

    tree = session_tree(session.session_dir)
    assert tree.agent is None  # session root
    (node,) = tree.children
    assert node.agent["task"] == "inner work"
    assert node.agent["status"] == "completed"
    # The child's calls reconstruct through the same view, one level down.
    (run,) = node.runs
    (call,) = run.calls
    assert call.input.verified
    assert call.input.messages[0].content == "child sys"
    assert node.children == []
