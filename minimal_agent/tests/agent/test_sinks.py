"""Tests for the built-in sinks: trace lines, blob interning, audit records."""

import json

from minimal_agent.agent.sinks import BlobStore, CallLogSink, RunLogSink, TraceSink
from minimal_agent.audit import read_run_records
from minimal_agent.events import (
    CallRequest,
    EventEmitter,
    InjectedBlock,
    RunEnd,
    RunEndStatus,
    RunStart,
    SessionCreated,
)


def _run_start(**overrides) -> RunStart:
    defaults = dict(
        model="test-model",
        backend="openai",
        tools_json='[{"name":"echo"}]',
        system_prompt="you are a test agent",
        store_len=0,
    )
    defaults.update(overrides)
    return RunStart(**defaults)


def _run_end(**overrides) -> RunEnd:
    defaults = dict(status=RunEndStatus.COMPLETED, calls=1, duration_ms=100)
    defaults.update(overrides)
    return RunEnd(**defaults)


def _call_request(**overrides) -> CallRequest:
    defaults = dict(
        projected=[(0, 2)],
        store_len=2,
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


def _run_records(session_dir) -> list[dict]:
    return [
        json.loads(line)
        for line in (session_dir / "runs.jsonl").read_text().splitlines()
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
    # Run-level audit facts are stripped from the run.start trace line.
    assert "tools_json" not in run_line["payload"]
    assert "system_prompt" not in run_line["payload"]
    for field in ("injected_run", "injected_call", "projected"):
        assert field not in call_line["payload"]
    # The slim fields still ride the trace.
    assert call_line["payload"]["store_len"] == 2
    assert call_line["payload"]["assembled_sha256"] == "sha256:abc"
    raw = (tmp_path / "events.jsonl").read_text()
    assert "you are a test agent" not in raw
    assert "injected!" not in raw


# ---- BlobStore --------------------------------------------------------------


def test_blob_store_writes_content_addressed_file_once(tmp_path):
    store = BlobStore(tmp_path / "blobs")

    ref = store.put("hello")
    assert ref.startswith("sha256:")

    digest = ref.removeprefix("sha256:")
    blob_path = tmp_path / "blobs" / digest
    assert blob_path.read_text() == "hello"
    assert store.put("hello") == ref
    # Write-once: exactly one file, no temp leftovers.
    assert [p.name for p in (tmp_path / "blobs").iterdir()] == [digest]


def test_blob_store_repeat_put_does_no_io(tmp_path, monkeypatch):
    store = BlobStore(tmp_path / "blobs")
    ref = store.put("hello")

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected I/O on repeat put")

    monkeypatch.setattr("pathlib.Path.write_text", _fail)
    monkeypatch.setattr("pathlib.Path.mkdir", _fail)

    assert store.put("hello") == ref


def test_blob_store_distinct_content_distinct_blobs(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    assert store.put("a") != store.put("b")
    assert len(list((tmp_path / "blobs").iterdir())) == 2


# ---- RunLogSink -------------------------------------------------------------


def test_run_log_sink_writes_open_row_at_start_and_close_row_at_end(tmp_path):
    emitter = EventEmitter(sinks=[RunLogSink(tmp_path)])

    emitter.emit(_run_start())
    # Identity is on disk the moment the run opens (span-style).
    (open_row,) = _run_records(tmp_path)
    assert open_row["phase"] == "open"
    assert open_row["status"] == "running"
    assert open_row["model"] == "test-model"
    assert open_row["backend"] == "openai"
    tools_blob = tmp_path / "blobs" / open_row["tools"].removeprefix("sha256:")
    assert tools_blob.read_text() == '[{"name":"echo"}]'
    prompt_blob = tmp_path / "blobs" / open_row["system_prompt"].removeprefix("sha256:")
    assert prompt_blob.read_text() == "you are a test agent"
    assert open_row["ts_start"]

    emitter.emit(_call_request())  # ignored by RunLogSink
    emitter.emit(_run_end(calls=1))

    open_row, close_row = _run_records(tmp_path)
    assert close_row["phase"] == "close"
    assert close_row["status"] == "completed"
    assert close_row["calls"] == 1
    assert close_row["duration_ms"] == 100
    assert close_row["ts_end"]

    # The merged view: identity from open, outcome from close.
    merged = read_run_records(tmp_path)
    assert len(merged) == 1
    (run,) = merged
    assert run["model"] == "test-model"
    assert run["system_prompt"] == open_row["system_prompt"]
    assert run["status"] == "completed"  # close row supersedes "running"
    assert run["calls"] == 1
    assert run["ts_start"] and run["ts_end"]


def test_run_log_sink_open_row_only_reads_as_running(tmp_path):
    """A run that never closes keeps its fingerprint and reads as running."""
    emitter = EventEmitter(sinks=[RunLogSink(tmp_path)])

    emitter.emit(_run_start())  # no run.end (crash / in-flight)

    (run,) = read_run_records(tmp_path)
    assert run["status"] == "running"
    assert run["model"] == "test-model"  # fingerprint still recoverable
    assert run["system_prompt"] is not None
    assert run["duration_ms"] is None


def test_run_log_sink_null_system_prompt(tmp_path):
    emitter = EventEmitter(sinks=[RunLogSink(tmp_path)])

    emitter.emit(_run_start(system_prompt=None))
    emitter.emit(_run_end())

    (run,) = read_run_records(tmp_path)
    assert run["system_prompt"] is None
    assert run["tools"] is not None  # tools still interned


# ---- CallLogSink ------------------------------------------------------------


def test_call_log_sink_records_only_per_call_facts(tmp_path):
    emitter = EventEmitter(sinks=[CallLogSink(tmp_path)])

    emitter.emit(_run_start())
    emitter.emit(_call_request())

    (record,) = _call_records(tmp_path)
    assert record["v"] == 2
    # Run-level facts are NOT on the call record — they live in runs.jsonl.
    for field in ("model", "backend", "tools", "system_prompt"):
        assert field not in record
    assert record["projected"] == [[0, 2]]
    assert record["injected"]["run"] == {"anchor": 0, "text": "injected!"}
    assert record["injected"]["call"] is None
    assert record["assembled_sha256"] == "sha256:abc"
    assert record["call_id"] == f"{record['run_id']}:c1"


def test_call_log_sink_ignores_non_call_events(tmp_path):
    emitter = EventEmitter(sinks=[CallLogSink(tmp_path)])

    emitter.emit(SessionCreated())
    emitter.emit(_run_start())

    assert not (tmp_path / "calls.jsonl").exists()


# ---- degradation ------------------------------------------------------------


def test_sinks_swallow_unwritable_directory(tmp_path):
    missing = tmp_path / "gone"  # never created — appends fail with OSError
    emitter = EventEmitter(
        sinks=[TraceSink(missing), RunLogSink(missing), CallLogSink(missing)]
    )

    emitter.emit(_run_start())
    emitter.emit(_call_request())  # must not raise
    emitter.emit(_run_end())  # must not raise

    assert not missing.exists()
