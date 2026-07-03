"""Tests for the built-in sinks: trace lines, blob interning, audit records."""

import json

from minimal_agent.agent.sinks import BlobStore, CallLogSink, TraceSink
from minimal_agent.events import (
    CallRequest,
    EventEmitter,
    InjectedBlock,
    RunStart,
    SessionCreated,
)


def _run_start(**overrides) -> RunStart:
    defaults = dict(
        model="test-model",
        backend="openai",
        tools_json='[{"name":"echo"}]',
        store_len=0,
    )
    defaults.update(overrides)
    return RunStart(**defaults)


def _call_request(**overrides) -> CallRequest:
    defaults = dict(
        projected=[(0, 2)],
        store_len=2,
        system_prompt="you are a test agent",
        injected_run=InjectedBlock(anchor=0, text="injected!"),
        injected_call=None,
        assembled_sha256="sha256:abc",
    )
    defaults.update(overrides)
    return CallRequest(**defaults)


def _trace_lines(session_dir) -> list[dict]:
    return [
        json.loads(line)
        for line in (session_dir / "events.jsonl").read_text().splitlines()
    ]


def _call_records(session_dir) -> list[dict]:
    return [
        json.loads(line)
        for line in (session_dir / "calls.jsonl").read_text().splitlines()
    ]


# ---- TraceSink --------------------------------------------------------------


def test_trace_sink_writes_one_json_line_per_envelope(tmp_path):
    emitter = EventEmitter(sinks=[TraceSink(tmp_path)])

    emitter.emit(SessionCreated())
    emitter.emit(_run_start())

    lines = _trace_lines(tmp_path)
    assert [line["type"] for line in lines] == ["session.created", "run.start"]
    assert lines[1]["payload"]["model"] == "test-model"
    assert lines[1]["run_id"].startswith("r-")


def test_trace_sink_never_carries_audit_owned_fields(tmp_path):
    emitter = EventEmitter(sinks=[TraceSink(tmp_path)])

    emitter.emit(_run_start())
    emitter.emit(_call_request())

    run_line, call_line = _trace_lines(tmp_path)
    assert "tools_json" not in run_line["payload"]
    for field in ("system_prompt", "injected_run", "injected_call", "projected"):
        assert field not in call_line["payload"]
    # The slim fields still ride the trace.
    assert call_line["payload"]["store_len"] == 2
    assert call_line["payload"]["assembled_sha256"] == "sha256:abc"
    raw = (tmp_path / "events.jsonl").read_text()
    assert "you are a test agent" not in raw
    assert "injected!" not in raw


# ---- BlobStore --------------------------------------------------------------


def test_blob_store_writes_content_addressed_file_once(tmp_path):
    store = BlobStore(tmp_path)

    ref = store.put("hello")
    assert ref.startswith("sha256:")

    digest = ref.removeprefix("sha256:")
    blob_path = tmp_path / "blobs" / digest
    assert blob_path.read_text() == "hello"
    assert store.put("hello") == ref
    # Write-once: exactly one file, no temp leftovers.
    assert [p.name for p in (tmp_path / "blobs").iterdir()] == [digest]


def test_blob_store_repeat_put_does_no_io(tmp_path, monkeypatch):
    store = BlobStore(tmp_path)
    ref = store.put("hello")

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected I/O on repeat put")

    monkeypatch.setattr("pathlib.Path.write_text", _fail)
    monkeypatch.setattr("pathlib.Path.mkdir", _fail)

    assert store.put("hello") == ref


def test_blob_store_distinct_content_distinct_blobs(tmp_path):
    store = BlobStore(tmp_path)
    assert store.put("a") != store.put("b")
    assert len(list((tmp_path / "blobs").iterdir())) == 2


# ---- CallLogSink ------------------------------------------------------------


def test_call_log_sink_stamps_remembered_fingerprint(tmp_path):
    emitter = EventEmitter(sinks=[CallLogSink(tmp_path)])

    emitter.emit(_run_start())
    emitter.emit(_call_request())

    (record,) = _call_records(tmp_path)
    assert record["model"] == "test-model"
    assert record["backend"] == "openai"
    tools_blob = tmp_path / "blobs" / record["tools"].removeprefix("sha256:")
    assert tools_blob.read_text() == '[{"name":"echo"}]'
    prompt_blob = tmp_path / "blobs" / record["system_prompt"].removeprefix("sha256:")
    assert prompt_blob.read_text() == "you are a test agent"
    assert record["projected"] == [[0, 2]]
    assert record["injected"]["run"] == {"anchor": 0, "text": "injected!"}
    assert record["injected"]["call"] is None
    assert record["call_id"] == f"{record['run_id']}:c1"


def test_call_log_sink_without_run_start_writes_null_fingerprint(tmp_path):
    emitter = EventEmitter(sinks=[CallLogSink(tmp_path)])

    emitter.emit(_call_request())

    (record,) = _call_records(tmp_path)
    assert record["model"] is None
    assert record["backend"] is None
    assert record["tools"] is None
    # Call-side facts are still recorded.
    assert record["system_prompt"] is not None


def test_call_log_sink_ignores_non_call_events(tmp_path):
    emitter = EventEmitter(sinks=[CallLogSink(tmp_path)])

    emitter.emit(SessionCreated())
    emitter.emit(_run_start())

    assert not (tmp_path / "calls.jsonl").exists()


# ---- degradation ------------------------------------------------------------


def test_sinks_swallow_unwritable_directory(tmp_path):
    missing = tmp_path / "gone"  # never created — appends fail with OSError
    emitter = EventEmitter(sinks=[TraceSink(missing), CallLogSink(missing)])

    emitter.emit(_run_start())
    emitter.emit(_call_request())  # must not raise

    assert not missing.exists()
