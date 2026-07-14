"""Tests for the audit reader: on-demand reconstruction from a session dir."""

import json
from typing import ClassVar
from unittest.mock import ANY, AsyncMock

import pytest
from pydantic import BaseModel

from minimal_agent.agent import Agent
from minimal_agent.agent.context import Context
from minimal_agent.agent.session import SessionManager
from minimal_agent.audit import (
    CallRecordNotFoundError,
    find_agent_scope,
    read_call_records,
    read_events,
    reconstruct_call,
    run_summaries,
    session_runs,
    single_run,
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
        behavior_prompt="you are helpful",
    )
    defaults.update(create_overrides)
    session = SessionManager(base_dir=tmp_path).create_session(**defaults)
    events = session.context.events
    events.emit(
        RunStart(
            model=defaults["model"],
            backend=defaults["backend"],
            tools_json="[]",
            system_prompt=defaults["behavior_prompt"],
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
        tmp_path, workspace_root=str(ws), context_sources=[_RunSource()]
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
        session_manager=SessionManager(base_dir=tmp_path / "sessions"),
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
        "reasoning_tokens": None,
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
        model="test-model", backend="openai", behavior_prompt="you are helpful"
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
        model="test-model", backend="openai", behavior_prompt="root sys"
    )

    with session.scope.child(spawned_by="t", task="x") as child:
        ctx = child.new_context(behavior_prompt="child sys")
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
        model="test-model", backend="openai", behavior_prompt="sys"
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
        model="test-model", backend="openai", behavior_prompt="sys"
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


async def test_single_run_scopes_to_one_run(tmp_path):
    """single_run returns exactly the run asked for, matching what
    session_runs produces for that id — across a session with two runs."""
    session = SessionManager(base_dir=tmp_path).create_session(
        model="test-model", backend="openai", behavior_prompt="sys"
    )
    scope = session.scope

    run_ids = []
    for turn in ("first", "second"):
        scope.events.emit(
            RunStart(
                model="test-model",
                backend="openai",
                tools_json="[]",
                system_prompt=None,
                store_len=len(session.context.store),
            )
        )
        run_ids.append(scope.events.run_id)
        session.context.add(Message(role=Role.USER, content=turn))
        await session.context.assemble()
        scope.events.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=1))

    all_runs = {r.run_id: r for r in session_runs(session.session_dir)}
    assert set(all_runs) == set(run_ids)

    for run_id in run_ids:
        one = single_run(session.session_dir, run_id)
        assert one == all_runs[run_id]


def test_single_run_unknown_id_returns_none(tmp_path):
    session = SessionManager(base_dir=tmp_path).create_session(
        model="test-model", backend="openai", behavior_prompt="sys"
    )
    assert single_run(session.session_dir, "r-does-not-exist") is None


async def test_run_summaries_index_matches_session_runs(tmp_path):
    """run_summaries lists exactly the runs single_run can resolve, in order,
    with outcome facts — but without reconstructing any call."""
    session = SessionManager(base_dir=tmp_path).create_session(
        model="test-model", backend="openai", behavior_prompt="sys"
    )
    scope = session.scope
    run_ids = []
    for turn in ("first", "second"):
        scope.events.emit(
            RunStart(
                model="test-model",
                backend="openai",
                tools_json="[]",
                system_prompt=None,
                store_len=len(session.context.store),
            )
        )
        run_ids.append(scope.events.run_id)
        session.context.add(Message(role=Role.USER, content=turn))
        await session.context.assemble()
        scope.events.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=1))

    summaries = run_summaries(session.session_dir)
    assert [s.run_id for s in summaries] == run_ids  # run order preserved
    first = summaries[0]
    assert first.model == "test-model"
    assert first.backend == "openai"
    assert first.status == "completed"
    assert first.calls == 1
    # The index lists exactly what single_run() can resolve.
    for s in summaries:
        assert single_run(session.session_dir, s.run_id) is not None


async def test_run_summaries_includes_degraded_run(tmp_path):
    """A run recorded without a run frame (direct assemble()) has no
    runs.jsonl row but still shows up in the index with null metadata."""
    session = SessionManager(base_dir=tmp_path).create_session(
        model="test-model", backend="openai", behavior_prompt="sys"
    )
    session.context.add(Message(role=Role.USER, content="go"))
    await session.context.assemble()  # no RunStart emitted → degraded run

    (summary,) = run_summaries(session.session_dir)
    assert summary.status is None
    assert summary.model is None
    # Still resolvable through the per-run reader.
    assert single_run(session.session_dir, summary.run_id) is not None


async def test_find_agent_scope_resolves_nested_agent_by_id(tmp_path):
    """A spawned agent's scope is findable by id at any depth, and the same
    per-run readers apply to it directly."""
    session = SessionManager(base_dir=tmp_path).create_session(
        model="test-model", backend="openai", behavior_prompt="root sys"
    )

    # root → child → grandchild, each recording one run.
    with session.scope.child(spawned_by="t", task="child work") as child:
        with child.child(spawned_by="t", task="grandchild work") as grandchild:
            ctx = grandchild.new_context(behavior_prompt="gc sys")
            grandchild.events.emit(
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
            grandchild.events.emit(
                RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=1)
            )
            gc_id = grandchild.dir.name  # scope dir is named a-<id>
        child_id = child.dir.name

    # Both agents resolve by id, wherever they sit in the tree.
    assert find_agent_scope(session.session_dir, child_id) == child.dir
    gc_dir = find_agent_scope(session.session_dir, gc_id)
    assert gc_dir == grandchild.dir

    # The nested agent's own run reconstructs through the same readers.
    (summary,) = run_summaries(gc_dir)
    run = single_run(gc_dir, summary.run_id)
    (call,) = run.calls
    assert call.input.verified
    assert call.input.messages[0].content == "gc sys"

    assert find_agent_scope(session.session_dir, "a-nope") is None


# ---- reconstruction under a custom projection ------------------------------


class _WindowedContext(Context):
    """Sends only the last two stored messages to the LLM."""

    def project(self):
        return self._store.messages[-2:]


class _SummarizingContext(Context):
    """Synthesizes a message that is not in the store — no range refers to it,
    so the recipe must capture it by value."""

    def project(self):
        return [Message(role=Role.USER, content="summary of everything")]


class _ElidingContext(Context):
    """A miniature of the reporter's BrowserContext: identity below a
    threshold, rewriting above it. Past four stored messages it replaces every
    message but the last two with a redacted model_copy() — so a call's input
    interleaves store references with messages that exist only in memory."""

    THRESHOLD = 4

    def project(self):
        msgs = self._store.messages
        if len(msgs) <= self.THRESHOLD:
            return msgs
        return [
            # Elide to a *distinct* redaction per message, as a real elision
            # would (it keeps the text and drops the images) — identical
            # redactions would collapse into a single blob and hide whether
            # dedup works across calls.
            *(
                m.model_copy(update={"content": f"[elided {m.content}]"})
                for m in msgs[:-2]
            ),
            *msgs[-2:],
        ]


class _ReorderingContext(Context):
    """Selects stored messages out of order — expressible as ranges, just not
    ascending ones."""

    def project(self):
        msgs = self._store.messages
        return [*msgs[-2:], *msgs[:-2]]


async def _session_with_messages(tmp_path, context_cls, n=5):
    session = SessionManager(base_dir=tmp_path).create_session(
        model="test-model",
        backend="openai",
        behavior_prompt="you are helpful",
        context_cls=context_cls,
    )
    events = session.context.events
    events.emit(
        RunStart(
            model="test-model",
            backend="openai",
            tools_json="[]",
            system_prompt="you are helpful",
            store_len=len(session.context.store),
        )
    )
    for i in range(n):
        session.context.add(Message(role=Role.USER, content=f"m{i}"))
    assembled = await session.context.assemble()
    events.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=1))
    return session, assembled


async def test_reconstruct_replays_a_windowed_projection_verbatim(tmp_path):
    """The recorded ranges describe what project() actually returned, so a
    windowed session reconstructs exactly — and verifies."""
    session, assembled = await _session_with_messages(tmp_path, _WindowedContext)

    (record,) = read_call_records(session.session_dir)
    assert record["projected"] == [[3, 5]]  # the last two of five, not [0, 5]

    result = reconstruct_call(session.session_dir, record["call_id"])

    assert result.messages == assembled
    assert result.verified
    assert [m.content for m in result.messages[1:]] == ["m3", "m4"]


async def test_synthesizing_projection_rebuilds_from_blobs(tmp_path):
    """A message the store never held is quoted into the record by value, so
    even a wholly synthetic projection reconstructs and verifies."""
    session, assembled = await _session_with_messages(tmp_path, _SummarizingContext)

    (record,) = read_call_records(session.session_dir)
    assert [set(e) for e in record["projected"]] == [{"blob"}]

    result = reconstruct_call(session.session_dir, record["call_id"])

    assert result.messages == assembled
    assert result.verified
    assert result.unverified_reason is None
    assert result.messages[1].content == "summary of everything"


async def test_eliding_projection_rebuilds_the_elided_content(tmp_path):
    """The load-bearing round trip: a rewriting projection (the reporter's
    case) verifies, its recipe interleaves blobs with store ranges, and the
    transcript still holds the originals — elision must never leak into the
    durable store."""
    session, assembled = await _session_with_messages(tmp_path, _ElidingContext, n=5)

    (record,) = read_call_records(session.session_dir)
    # Three rewritten messages by value, then the two untouched ones by range.
    assert record["projected"] == [
        *[{"blob": ANY}] * 3,
        [3, 5],
    ]

    result = reconstruct_call(session.session_dir, record["call_id"])

    assert result.messages == assembled
    assert result.verified
    assert [m.content for m in result.messages[1:]] == [
        "[elided m0]",
        "[elided m1]",
        "[elided m2]",
        "m3",
        "m4",
    ]
    # Invariant: the store holds originals, only.
    assert [m.content for m in session.context.store.messages] == [
        f"m{i}" for i in range(5)
    ]


async def test_reordering_projection_records_ranges_in_projected_order(tmp_path):
    """Reordering is a selection, so it costs no blobs — the ranges just come
    in the order the model saw them, which the old ascending-only vocabulary
    could not express."""
    session, assembled = await _session_with_messages(tmp_path, _ReorderingContext)

    (record,) = read_call_records(session.session_dir)
    assert record["projected"] == [[3, 5], [0, 3]]

    result = reconstruct_call(session.session_dir, record["call_id"])

    assert result.messages == assembled
    assert result.verified
    assert [m.content for m in result.messages[1:]] == ["m3", "m4", "m0", "m1", "m2"]


async def test_selecting_projection_writes_no_blobs(tmp_path):
    """Zero cost when unused: a pure-selection projection's record is
    equivalent to a pre-v3 one, and interns nothing."""
    session, _ = await _session_with_messages(tmp_path, _WindowedContext)

    (record,) = read_call_records(session.session_dir)
    assert record["projected"] == [[3, 5]]

    # Only the run's own blobs (system prompt, tool schemas) — no message ones.
    blobs = session.session_dir / "blobs"
    assert len(list(blobs.iterdir())) == 2


async def test_identically_elided_messages_share_one_blob(tmp_path):
    """Content addressing makes repetition free: the same elision across two
    calls is one blob on disk, referenced twice."""
    session, _ = await _session_with_messages(tmp_path, _ElidingContext, n=5)
    await session.context.assemble()  # a second call, eliding identically

    first, second = read_call_records(session.session_dir)
    refs = [e["blob"] for e in first["projected"] if isinstance(e, dict)]
    assert refs == [e["blob"] for e in second["projected"] if isinstance(e, dict)]

    for ref in set(refs):
        assert (session.session_dir / "blobs" / ref.removeprefix("sha256:")).exists()
    # Three distinct elided messages, written once each despite two calls.
    assert len(set(refs)) == 3


async def test_legacy_null_projection_stays_unverifiable(tmp_path):
    """A pre-v3 record whose rewriting projection had no range expression was
    never persisted, so it does not retroactively become rebuildable — it
    reconstructs unverified, with the reason."""
    session, _ = await _session_with_messages(tmp_path, _WindowedContext)
    calls = session.session_dir / "calls.jsonl"
    record = json.loads(calls.read_text())
    record["v"] = 2
    record["projected"] = None
    calls.write_text(json.dumps(record) + "\n")

    result = reconstruct_call(session.session_dir, record["call_id"])

    assert not result.verified
    assert "not expressible as store ranges" in result.unverified_reason
