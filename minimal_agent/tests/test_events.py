"""Tests for the event seam: envelope stamping, id minting, and fan-out."""

from minimal_agent.events import (
    CallRequest,
    CallResponse,
    Envelope,
    EventEmitter,
    RunEnd,
    RunEndStatus,
    RunStart,
    SessionCreated,
    ToolEnd,
    ToolStart,
    ToolStatus,
)


class _Recorder:
    """Sink that keeps every envelope it receives."""

    def __init__(self):
        self.envelopes: list[Envelope] = []

    def handle(self, env: Envelope) -> None:
        self.envelopes.append(env)


class _Exploding:
    """Sink whose handle always raises."""

    def handle(self, env: Envelope) -> None:
        raise RuntimeError("sink blew up")


def _run_start(**overrides) -> RunStart:
    defaults = dict(
        model="test-model",
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


# ---- fan-out ----------------------------------------------------------------


def test_every_sink_receives_every_envelope():
    a, b = _Recorder(), _Recorder()
    emitter = EventEmitter(sinks=[a, b])

    emitter.emit(SessionCreated())
    emitter.emit(_run_start())

    assert len(a.envelopes) == 2
    assert [e.event for e in a.envelopes] == [e.event for e in b.envelopes]


def test_raising_sink_is_skipped_and_others_still_receive():
    recorder = _Recorder()
    emitter = EventEmitter(sinks=[_Exploding(), recorder])

    emitter.emit(SessionCreated())  # must not raise

    assert len(recorder.envelopes) == 1


# ---- id minting -------------------------------------------------------------


def test_run_start_mints_run_id_and_resets_call_numbering():
    recorder = _Recorder()
    emitter = EventEmitter(sinks=[recorder])

    emitter.emit(_run_start())
    emitter.emit(_call_request())
    emitter.emit(_call_request())
    emitter.emit(_run_start())
    emitter.emit(_call_request())

    envs = recorder.envelopes
    first_run, second_run = envs[0].run_id, envs[3].run_id
    assert first_run and first_run.startswith("r-")
    assert second_run != first_run
    assert envs[1].call_id == f"{first_run}:c1"
    assert envs[2].call_id == f"{first_run}:c2"
    # Numbering resets with the new run.
    assert envs[4].call_id == f"{second_run}:c1"


def test_call_scoped_events_carry_current_call_id():
    recorder = _Recorder()
    emitter = EventEmitter(sinks=[recorder])

    emitter.emit(_run_start())
    emitter.emit(_call_request())
    emitter.emit(CallResponse(latency_ms=1, usage=None, tool_calls=1))
    emitter.emit(ToolStart(tool_call_id="tc_1", name="echo"))
    emitter.emit(
        ToolEnd(tool_call_id="tc_1", name="echo", status=ToolStatus.OK, duration_ms=1)
    )

    call_id = recorder.envelopes[1].call_id
    assert call_id is not None
    assert all(e.call_id == call_id for e in recorder.envelopes[1:])


def test_run_scoped_events_have_null_call_id():
    recorder = _Recorder()
    emitter = EventEmitter(sinks=[recorder])

    emitter.emit(SessionCreated())
    emitter.emit(_run_start())
    emitter.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=0, duration_ms=1))

    assert all(e.call_id is None for e in recorder.envelopes)
    # Session-scoped: no run id either.
    assert recorder.envelopes[0].run_id is None


def test_call_request_without_run_start_degrades_to_synthetic_run_id():
    recorder = _Recorder()
    emitter = EventEmitter(sinks=[recorder])

    emitter.emit(_call_request())

    env = recorder.envelopes[0]
    assert env.run_id and env.run_id.startswith("r-")
    assert env.call_id == f"{env.run_id}:c1"


# ---- envelope stamps --------------------------------------------------------


def test_envelope_stamps_version_and_utc_timestamp():
    recorder = _Recorder()
    emitter = EventEmitter(sinks=[recorder])

    emitter.emit(SessionCreated())

    env = recorder.envelopes[0]
    assert env.v == 2
    assert env.ts.endswith("Z")
    assert "T" in env.ts
