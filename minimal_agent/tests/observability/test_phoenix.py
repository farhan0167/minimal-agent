"""Tests for the PhoenixSink event -> OTel span translator.

No live Phoenix, no network: an `InMemorySpanExporter` + `SimpleSpanProcessor`
capture the spans the sink produces, and the assertions read the exported
`ReadableSpan` list. The whole module skips when opentelemetry-sdk (the
`phoenix` extra) is not installed — the sink is import-guarded on it.

Spans are driven through a real `EventEmitter` so envelopes are stamped exactly
as in production: correct call-id minting, and the `agent_id` the emitter
carries for a child scope. That `agent_id` is the correlation that lets a
nested agent's CHAIN span parent under the parent's AGENT span.
"""

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

from minimal_agent.events import (  # noqa: E402
    AgentEnd,
    AgentEndStatus,
    AgentSpawn,
    CallRequest,
    CallResponse,
    EventEmitter,
    RunEnd,
    RunEndStatus,
    RunStart,
    ToolEnd,
    ToolStart,
    ToolStatus,
)
from minimal_agent.observability.phoenix import PhoenixSink  # noqa: E402


@pytest.fixture
def harness():
    """A PhoenixSink wired to an in-memory exporter, plus its span reader."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    sink = PhoenixSink(tracer)
    return sink, exporter


def _run_start(**overrides) -> RunStart:
    defaults = dict(
        model="gpt-4o-mini",
        backend="openai",
        tools_json="[]",
        system_prompt=None,
        store_len=0,
    )
    defaults.update(overrides)
    return RunStart(**defaults)


def _call_request() -> CallRequest:
    return CallRequest(
        projected=[(0, 1)],
        store_len=1,
        injected_run=None,
        injected_call=None,
        assembled_sha256="sha256:0",
    )


def _spans_by_name(exporter):
    return {s.name: s for s in exporter.get_finished_spans()}


def _attr(span, key):
    return span.attributes.get(key)


# ---- basic pairing ---------------------------------------------------------


def test_run_open_close_yields_one_chain_span(harness):
    sink, exporter = harness
    emitter = EventEmitter(sinks=[sink])

    emitter.emit(_run_start())
    emitter.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=0, duration_ms=10))

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    run = spans[0]
    assert run.name == "run"
    assert _attr(run, "openinference.span.kind") == "CHAIN"
    assert _attr(run, "llm.model_name") == "gpt-4o-mini"
    assert _attr(run, "llm.provider") == "openai"
    assert _attr(run, "minimal_agent.run_status") == "completed"


def test_call_span_carries_usage_and_nests_under_run(harness):
    sink, exporter = harness
    emitter = EventEmitter(sinks=[sink])

    emitter.emit(_run_start())
    emitter.emit(_call_request())
    emitter.emit(
        CallResponse(
            latency_ms=1180,
            usage={"prompt_tokens": 900, "completion_tokens": 60, "total_tokens": 960},
            tool_calls=0,
        )
    )
    emitter.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=20))

    by_name = _spans_by_name(exporter)
    call = by_name["llm_call"]
    run = by_name["run"]
    assert _attr(call, "openinference.span.kind") == "LLM"
    # the run fingerprint is stamped onto the call span
    assert _attr(call, "llm.model_name") == "gpt-4o-mini"
    assert _attr(call, "llm.token_count.prompt") == 900
    assert _attr(call, "llm.token_count.completion") == 60
    assert _attr(call, "llm.token_count.total") == 960
    assert _attr(call, "minimal_agent.latency_ms") == 1180
    # nesting: the call span's parent is the run span
    assert call.parent.span_id == run.context.span_id


def test_tool_span_nests_under_call_and_records_status(harness):
    sink, exporter = harness
    emitter = EventEmitter(sinks=[sink])

    emitter.emit(_run_start())
    emitter.emit(_call_request())
    emitter.emit(ToolStart(tool_call_id="tc_a", name="run_shell"))
    emitter.emit(
        ToolEnd(
            tool_call_id="tc_a",
            name="run_shell",
            status=ToolStatus.OK,
            duration_ms=42,
        )
    )
    emitter.emit(CallResponse(latency_ms=1, usage=None, tool_calls=1))
    emitter.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=20))

    by_name = _spans_by_name(exporter)
    tool = by_name["tool:run_shell"]
    call = by_name["llm_call"]
    assert _attr(tool, "openinference.span.kind") == "TOOL"
    assert _attr(tool, "tool.name") == "run_shell"
    assert _attr(tool, "tool_call.id") == "tc_a"
    assert _attr(tool, "minimal_agent.tool_status") == "ok"
    assert tool.parent.span_id == call.context.span_id
    assert tool.status.is_ok


def test_errored_tool_span_is_marked_error(harness):
    sink, exporter = harness
    emitter = EventEmitter(sinks=[sink])

    emitter.emit(_run_start())
    emitter.emit(_call_request())
    emitter.emit(ToolStart(tool_call_id="tc_a", name="run_shell"))
    emitter.emit(
        ToolEnd(
            tool_call_id="tc_a",
            name="run_shell",
            status=ToolStatus.ERROR,
            duration_ms=5,
        )
    )
    emitter.emit(CallResponse(latency_ms=1, usage=None, tool_calls=1))
    emitter.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=20))

    tool = _spans_by_name(exporter)["tool:run_shell"]
    from opentelemetry.trace import StatusCode

    assert tool.status.status_code == StatusCode.ERROR
    assert _attr(tool, "minimal_agent.tool_status") == "error"


# ---- nesting across the emitter boundary -----------------------------------


def test_nested_agent_run_nests_under_agent_span(harness):
    sink, exporter = harness
    # Parent scope emitter (session root: agent_id=None) and a child scope
    # emitter carrying the spawned agent's id — exactly how RecordedScope wires
    # a child. Both feed the same sink instance.
    parent = EventEmitter(sinks=[sink])
    child = EventEmitter(sinks=[sink], agent_id="a-child01")

    # parent: run -> call -> (spawn the child) -> ...
    parent.emit(_run_start())
    parent.emit(_call_request())
    parent.emit(
        AgentSpawn(
            agent_id="a-child01",
            spawned_by="spawn_agents",
            task="do a thing",
            tool_call_id="tc_a",
        )
    )
    # child scope: its own run + call, emitted on the child emitter
    child.emit(_run_start(model="gpt-4o-mini"))
    child.emit(_call_request())
    child.emit(CallResponse(latency_ms=1, usage=None, tool_calls=0))
    child.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=5))
    # child ends, parent finishes
    parent.emit(
        AgentEnd(
            agent_id="a-child01",
            status=AgentEndStatus.COMPLETED,
            duration_ms=6,
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )
    )
    parent.emit(CallResponse(latency_ms=1, usage=None, tool_calls=1))
    parent.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=20))

    spans = {s.name: s for s in exporter.get_finished_spans()}
    ids = {s.context.span_id: s for s in exporter.get_finished_spans()}

    agent_span = spans["agent:spawn_agents"]
    assert _attr(agent_span, "openinference.span.kind") == "AGENT"
    assert _attr(agent_span, "minimal_agent.agent_id") == "a-child01"
    assert _attr(agent_span, "llm.token_count.total") == 2

    # There are two CHAIN spans and two LLM spans (parent + child). Find the
    # child run by walking parent links up from the child's agent span.
    chain_spans = [s for s in exporter.get_finished_spans() if s.name == "run"]
    assert len(chain_spans) == 2
    child_run = next(
        s
        for s in chain_spans
        if s.parent and s.parent.span_id == agent_span.context.span_id
    )
    # the child run chains up: child_run -> agent_span -> parent_call -> parent_run
    assert child_run.parent.span_id == agent_span.context.span_id
    agent_parent = ids[agent_span.parent.span_id]
    assert agent_parent.name == "llm_call"
    grandparent = ids[agent_parent.parent.span_id]
    assert grandparent.name == "run"
    assert grandparent.parent is None  # root of the trace


# ---- crash / orphan sweep --------------------------------------------------


def test_run_end_sweeps_orphaned_open_call_span(harness):
    sink, exporter = harness
    emitter = EventEmitter(sinks=[sink])

    # crash variant: call.request with tool, no call.response, then run.end
    emitter.emit(_run_start())
    emitter.emit(_call_request())
    emitter.emit(ToolStart(tool_call_id="tc_a", name="run_shell"))
    emitter.emit(
        ToolEnd(
            tool_call_id="tc_a",
            name="run_shell",
            status=ToolStatus.OK,
            duration_ms=42,
        )
    )
    # process dies here — no call.response for c1
    emitter.emit(RunEnd(status=RunEndStatus.ERROR, calls=1, duration_ms=51))

    from opentelemetry.trace import StatusCode

    by_name = _spans_by_name(exporter)
    # the tool closed normally; the call was force-closed as an orphan
    assert by_name["tool:run_shell"].status.is_ok
    call = by_name["llm_call"]
    assert _attr(call, "minimal_agent.orphaned") is True
    assert call.status.status_code == StatusCode.ERROR
    # the run itself is ERROR
    run = by_name["run"]
    assert run.status.status_code == StatusCode.ERROR
    assert _attr(run, "minimal_agent.run_status") == "error"


# ---- fire-and-forget -------------------------------------------------------


def test_translation_error_does_not_propagate(harness, monkeypatch):
    sink, exporter = harness
    emitter = EventEmitter(sinks=[sink])

    def boom(env):
        raise RuntimeError("translator blew up")

    monkeypatch.setattr(sink, "_dispatch", boom)

    # must not raise — handle() swallows and logs
    emitter.emit(_run_start())
    emitter.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=0, duration_ms=1))

    # nothing exported (every dispatch raised), but the run survived
    assert exporter.get_finished_spans() == ()


def test_sink_never_breaks_the_emitter_for_other_sinks(harness):
    sink, exporter = harness

    class _Recorder:
        def __init__(self):
            self.count = 0

        def handle(self, env):
            self.count += 1

    other = _Recorder()
    emitter = EventEmitter(sinks=[sink, other])

    emitter.emit(_run_start())
    emitter.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=0, duration_ms=1))

    # the other sink saw both envelopes regardless of the phoenix sink
    assert other.count == 2
    assert len(exporter.get_finished_spans()) == 1


# ---- integration through the real scope tree -------------------------------


def test_child_scope_wiring_carries_agent_id_end_to_end(harness, tmp_path):
    """The nesting correlation must survive the real Scope machinery, not just
    hand-fed emitters: RecordedScope.child() has to stamp the child's agent_id
    onto its emitter, or the child's CHAIN span can't find its AGENT parent."""
    from minimal_agent.agent.scope import RecordedScope
    from minimal_agent.agent.sinks import BlobStore

    sink, exporter = harness
    root = RecordedScope(
        tmp_path,
        blobs=BlobStore(tmp_path / "blobs"),
        session_id="sess-1",
        extra_sinks=[sink],
    )

    # A run on the root that opens a child scope mid-call, exactly as a
    # spawn tool would (agent.spawn/agent.end come from the context manager).
    root.events.emit(_run_start())
    root.events.emit(_call_request())
    with root.child(spawned_by="spawn_agents", task="t", tool_call_id="tc_a") as child:
        child.events.emit(_run_start())
        child.events.emit(_call_request())
        child.events.emit(CallResponse(latency_ms=1, usage=None, tool_calls=0))
        child.events.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=5))
    root.events.emit(CallResponse(latency_ms=1, usage=None, tool_calls=1))
    root.events.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=20))

    finished = exporter.get_finished_spans()
    ids = {s.context.span_id: s for s in finished}
    agent_span = next(s for s in finished if s.name.startswith("agent:"))
    chain_spans = [s for s in finished if s.name == "run"]
    assert len(chain_spans) == 2

    # the child run nests under the AGENT span — the agent_id made it across
    # the emitter boundary through the real scope wiring.
    child_run = next(
        s
        for s in chain_spans
        if s.parent and s.parent.span_id == agent_span.context.span_id
    )
    assert child_run is not None
    # and the AGENT span itself chains up to the root run
    agent_parent = ids[agent_span.parent.span_id]
    assert agent_parent.name == "llm_call"
    assert ids[agent_parent.parent.span_id].name == "run"


# ---- full=True: reconstructed input on the LLM span ------------------------


async def test_full_flattens_reconstructed_input_onto_llm_span(tmp_path):
    """full=True reconstructs the call's input from the on-disk artifacts and
    flattens it onto the LLM span, so Phoenix shows what the model saw. Driven
    through a real SessionManager session so the reconstruction reads genuine
    calls.jsonl / runs.jsonl / messages.jsonl / blobs, exactly as in prod."""
    from minimal_agent.agent.session import SessionManager
    from minimal_agent.events import RunStart
    from minimal_agent.llm.types import Message, Role

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    sink = PhoenixSink(provider.get_tracer("test"), full=True)

    session = SessionManager(base_dir=tmp_path, extra_sinks=[sink]).create_session(
        model="test-model",
        backend="openai",
        system_prompt="you are helpful",
        workspace_root=str(tmp_path),
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
    session.context.add(Message(role=Role.USER, content="what changed?"))
    # assemble() emits call.request, which CallLogSink writes to calls.jsonl —
    # so the reconstruction the sink runs at call.response has a complete recipe.
    await session.context.assemble()
    events.emit(CallResponse(latency_ms=5, usage=None, tool_calls=0, text="all good"))
    events.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=6))

    call = _spans_by_name(exporter)["llm_call"]
    # input: system prompt is message[0], the user turn is message[1]
    assert _attr(call, "llm.input_messages.0.message.role") == "system"
    assert _attr(call, "llm.input_messages.0.message.content") == "you are helpful"
    assert _attr(call, "llm.input_messages.1.message.role") == "user"
    assert _attr(call, "llm.input_messages.1.message.content") == "what changed?"
    assert _attr(call, "minimal_agent.input_verified") is True
    assert "what changed?" in _attr(call, "input.value")
    # output: the assistant reply rides the call.response event
    assert _attr(call, "llm.output_messages.0.message.role") == "assistant"
    assert _attr(call, "llm.output_messages.0.message.content") == "all good"
    assert _attr(call, "output.value") == "all good"


def test_full_output_records_tool_calls_when_the_reply_is_a_tool_request(harness):
    """A tool-calling reply (no text) lists the requested calls on the output."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    sink = PhoenixSink(provider.get_tracer("test"), full=True)
    emitter = EventEmitter(sinks=[sink])

    emitter.emit(_run_start())
    emitter.emit(_call_request())
    emitter.emit(
        CallResponse(
            latency_ms=1,
            usage=None,
            tool_calls=1,
            text=None,
            tool_calls_detail=[
                {"id": "tc_a", "name": "run_shell", "arguments": {"cmd": "ls"}}
            ],
        )
    )
    emitter.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=2))

    call = _spans_by_name(exporter)["llm_call"]
    assert _attr(call, "llm.output_messages.0.message.role") == "assistant"
    assert (
        _attr(
            call, "llm.output_messages.0.message.tool_calls.0.tool_call.function.name"
        )
        == "run_shell"
    )
    assert "run_shell" in _attr(call, "output.value")


def test_default_sink_omits_input_messages(harness):
    """Without full=True, no message bodies are exported — references only."""
    sink, exporter = harness
    emitter = EventEmitter(sinks=[sink])

    emitter.emit(_run_start())
    emitter.emit(_call_request())
    emitter.emit(CallResponse(latency_ms=1, usage=None, tool_calls=0))
    emitter.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=1, duration_ms=2))

    call = _spans_by_name(exporter)["llm_call"]
    assert _attr(call, "llm.input_messages.0.message.role") is None
    assert _attr(call, "input.value") is None
    assert _attr(call, "llm.output_messages.0.message.role") is None
    assert _attr(call, "output.value") is None
