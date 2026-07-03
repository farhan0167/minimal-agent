"""Tests for the audit reader: on-demand reconstruction from a session dir."""

from typing import ClassVar
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from minimal_agent.agent import Agent
from minimal_agent.agent.session import Session
from minimal_agent.audit import (
    CallRecordNotFoundError,
    read_call_records,
    read_events,
    reconstruct_call,
    session_runs,
)
from minimal_agent.context_sources import Placement
from minimal_agent.events import RunStart
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
    defaults = dict(
        model="test-model",
        backend="openai",
        system_prompt="you are helpful",
        base_dir=tmp_path,
    )
    defaults.update(create_overrides)
    session = Session.create(**defaults)
    session.context.add(Message(role=Role.USER, content="what changed?"))
    assembled = await session.context.assemble()
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
    # Direct assemble() with no run.start: fingerprint degrades to null.
    assert result.model is None
    assert result.tools is None


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
    session = Session.create(
        model="test-model", backend="openai", base_dir=tmp_path
    )
    (session.session_dir / "events.jsonl").unlink()

    assert read_events(session.session_dir) == []
    assert read_call_records(session.session_dir) == []


async def test_read_events_returns_timeline_in_order(tmp_path):
    session, _ = await _session_with_one_call(tmp_path)

    events = read_events(session.session_dir)

    assert [e["type"] for e in events] == ["session.created", "call.request"]


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
                tool_calls=[
                    ToolCall(id="tc_1", name="probe_tool", arguments={})
                ],
                usage=Usage(
                    prompt_tokens=10, completion_tokens=5, total_tokens=15
                ),
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
    )
    session = await agent.create_session(base_dir=tmp_path / "sessions")
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
    session, _ = await _session_with_one_call(tmp_path)

    (run,) = session_runs(session.session_dir)

    # No run.start was ever emitted: frame metadata is null but the call
    # is still present and fully reconstructed.
    assert run.started_at is None
    assert run.status is None
    (call,) = run.calls
    assert call.input.verified
    assert call.response is None  # no reply was ever stored
    assert call.latency_ms is None


def test_session_runs_empty_session(tmp_path):
    session = Session.create(
        model="test-model", backend="openai", base_dir=tmp_path
    )
    assert session_runs(session.session_dir) == []


async def test_reconstruct_carries_fingerprint_and_parsed_tools(tmp_path):
    session = Session.create(
        model="test-model", backend="openai", base_dir=tmp_path
    )
    session.context.events.emit(
        RunStart(
            model="test-model",
            backend="openai",
            tools_json='[{"name":"echo"}]',
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
