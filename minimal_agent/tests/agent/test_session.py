import hashlib
import json

import pytest

from minimal_agent.agent.context import Context, _merge_into_user
from minimal_agent.agent.session import SessionConfigMismatchError, SessionManager
from minimal_agent.context_sources import GitStatusSource
from minimal_agent.events import CallResponse, RunEnd, RunEndStatus, RunStart
from minimal_agent.llm.types import Message, Role, Usage

_MODEL = "gpt-4o-mini"
_BACKEND = "openai"


def _create(tmp_path, **overrides):
    """Helper to create a session with default model/backend."""
    defaults = dict(model=_MODEL, backend=_BACKEND)
    defaults.update(overrides)
    return SessionManager(base_dir=tmp_path).create_session(**defaults)


def _open_run(session, system_prompt=None) -> None:
    """Emit run.start the way the loop does — this is what interns the run's
    system-prompt blob and writes its runs.jsonl open row."""
    session.context.events.emit(
        RunStart(
            model=_MODEL,
            backend=_BACKEND,
            tools_json="[]",
            system_prompt=(
                system_prompt
                if system_prompt is not None
                else session.context.system_prompt
            ),
            store_len=len(session.context.store),
        )
    )


def _close_run(session, calls=1) -> None:
    session.context.events.emit(
        RunEnd(status=RunEndStatus.COMPLETED, calls=calls, duration_ms=1)
    )


def _load(session_id, tmp_path, **overrides):
    """Helper to load a session with default model/backend."""
    defaults = dict(model=_MODEL, backend=_BACKEND)
    defaults.update(overrides)
    return SessionManager(base_dir=tmp_path).load_session(session_id, **defaults)


def _report_usage(session, usage: Usage) -> None:
    """Report usage the way the loop does: a call.response on the scope."""
    session.scope.events.emit(
        CallResponse(latency_ms=1, usage=usage.model_dump(), tool_calls=0)
    )


def test_create_makes_directory_and_files(tmp_path):
    session = _create(tmp_path, behavior_prompt="sys")

    session_dir = tmp_path / session.session_id
    assert session_dir.is_dir()
    assert (session_dir / "session.json").exists()

    meta = json.loads((session_dir / "session.json").read_text())
    assert meta["session_id"] == session.session_id
    assert meta["model"] == _MODEL
    assert meta["backend"] == _BACKEND
    assert meta["usage"] is None


def test_add_message_writes_to_jsonl(tmp_path):
    session = _create(tmp_path, behavior_prompt="sys")
    session.context.add(Message(role=Role.USER, content="hello"))

    messages_path = tmp_path / session.session_id / "messages.jsonl"
    lines = messages_path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert Message.model_validate_json(lines[0]).content == "hello"


def test_load_recovers_messages(tmp_path):
    session = _create(tmp_path, behavior_prompt="sys")
    session.context.add(Message(role=Role.USER, content="q"))
    session.context.add(Message(role=Role.ASSISTANT, content="a"))
    sid = session.session_id

    loaded = _load(sid, tmp_path, behavior_prompt="sys")

    assert len(loaded.context.store) == 2
    assert loaded.context.store.messages[0].content == "q"
    assert loaded.context.store.messages[1].content == "a"


def test_load_uses_provided_system_prompt(tmp_path):
    session = _create(tmp_path, behavior_prompt="original")
    session.context.add(Message(role=Role.USER, content="hi"))
    sid = session.session_id

    loaded = _load(sid, tmp_path, behavior_prompt="updated")
    msgs = loaded.context.get_messages()

    assert msgs[0].role == Role.SYSTEM
    assert msgs[0].content == "updated"


def test_load_preserves_model_and_backend(tmp_path):
    session = _create(tmp_path)
    sid = session.session_id

    loaded = _load(sid, tmp_path)
    assert loaded.model == _MODEL
    assert loaded.backend == _BACKEND


def test_load_rejects_different_model(tmp_path):
    session = _create(tmp_path)
    sid = session.session_id

    with pytest.raises(SessionConfigMismatchError, match="model"):
        _load(sid, tmp_path, model="claude-3-opus")


def test_load_rejects_different_backend(tmp_path):
    session = _create(tmp_path)
    sid = session.session_id

    with pytest.raises(SessionConfigMismatchError, match="backend"):
        _load(sid, tmp_path, backend="anthropic")


def test_load_rejects_both_mismatched(tmp_path):
    session = _create(tmp_path)
    sid = session.session_id

    with pytest.raises(SessionConfigMismatchError) as exc_info:
        _load(sid, tmp_path, model="other-model", backend="anthropic")
    assert "model" in str(exc_info.value)
    assert "backend" in str(exc_info.value)


def test_usage_accumulates_from_call_response_events(tmp_path):
    """Accounting is a sink: call.response usage lands in session.json."""
    session = _create(tmp_path)

    u1 = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    _report_usage(session, u1)
    assert session.usage == u1

    u2 = Usage(prompt_tokens=200, completion_tokens=100, total_tokens=300)
    _report_usage(session, u2)

    assert session.usage is not None
    assert session.usage.prompt_tokens == 300
    assert session.usage.completion_tokens == 150
    assert session.usage.total_tokens == 450

    # Verify persisted to disk
    meta = json.loads((tmp_path / session.session_id / "session.json").read_text())
    assert meta["usage"]["prompt_tokens"] == 300


def test_usage_updates_timestamp(tmp_path):
    session = _create(tmp_path)
    original_updated = session.updated_at

    _report_usage(
        session, Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    )

    assert session.updated_at >= original_updated


def test_list_sessions_sorted_by_updated_at(tmp_path):
    s1 = _create(tmp_path)
    _report_usage(s1, Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2))

    s2 = _create(tmp_path)
    _report_usage(s2, Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2))

    sessions = SessionManager(base_dir=tmp_path).list_sessions()

    assert len(sessions) == 2
    # Most recently updated first
    assert sessions[0].session_id == s2.session_id
    assert sessions[1].session_id == s1.session_id


def test_read_meta_returns_metadata(tmp_path):
    session = _create(tmp_path, workspace_root="/some/workspace")
    sid = session.session_id

    meta = SessionManager(base_dir=tmp_path).read_meta(sid)

    assert meta.session_id == sid
    assert meta.model == _MODEL
    assert meta.backend == _BACKEND
    assert meta.workspace_root == "/some/workspace"


def test_read_meta_does_not_touch_messages(tmp_path):
    """read_meta reads only session.json — a corrupt JSONL is irrelevant."""
    session = _create(tmp_path)
    sid = session.session_id
    (tmp_path / sid / "messages.jsonl").write_text("not json at all\n")

    meta = SessionManager(base_dir=tmp_path).read_meta(sid)
    assert meta.session_id == sid


def test_read_meta_missing_session_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        SessionManager(base_dir=tmp_path).read_meta("no-such-session")


def test_workspace_root_property(tmp_path):
    session = _create(tmp_path, workspace_root="/some/workspace")
    assert session.workspace_root == "/some/workspace"

    bare = _create(tmp_path)
    assert bare.workspace_root is None


class _RunSource:
    """Minimal RUN-placed live source for passthrough tests."""

    name = "liveProbe"
    placement = "run"

    async def gather(self, env) -> str:
        return f"root={env.workspace_root}"


async def test_create_forwards_live_sources_to_context(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    session = _create(
        tmp_path,
        workspace_root=str(ws),
        context_sources=[_RunSource()],
    )
    session.context.add(Message(role=Role.USER, content="hi"))

    msgs = await session.context.assemble()

    assert '<context name="liveProbe">' in msgs[-1].content
    assert f"root={ws}" in msgs[-1].content


async def test_load_reattaches_live_sources_with_persisted_root(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    session = _create(tmp_path, workspace_root=str(ws))
    session.context.add(Message(role=Role.USER, content="hi"))
    sid = session.session_id

    loaded = _load(sid, tmp_path, context_sources=[_RunSource()])
    msgs = await loaded.context.assemble()

    # load() appends an interrupted-response marker after the unanswered
    # user message, so the anchor is the last *user* message, not the tail.
    merged = next(m for m in reversed(msgs) if m.role is Role.USER)
    assert f"root={ws}" in merged.content


async def test_load_without_persisted_root_degrades_silently(tmp_path):
    """A legacy session (no persisted workspace_root) still gathers — the env
    always exists — but hands sources workspace_root=None, and every built-in
    bows out with None rather than injecting a block about nowhere."""
    session = _create(tmp_path)  # legacy: no workspace_root
    session.context.add(Message(role=Role.USER, content="hi"))
    sid = session.session_id

    loaded = _load(sid, tmp_path, context_sources=[GitStatusSource()])
    msgs = await loaded.context.assemble()

    assert msgs == loaded.context.get_messages()


def test_list_sessions_empty_dir(tmp_path):
    sessions = SessionManager(base_dir=tmp_path).list_sessions()
    assert sessions == []


def test_list_sessions_nonexistent_dir(tmp_path):
    sessions = SessionManager(base_dir=tmp_path / "nope").list_sessions()
    assert sessions == []


# ---- observability artifacts (events.jsonl / calls.jsonl / blobs) -----------


def _events(session_dir) -> list[dict]:
    return [
        json.loads(line)
        for line in (session_dir / "events.jsonl").read_text().splitlines()
    ]


def _calls(session_dir) -> list[dict]:
    return [
        json.loads(line)
        for line in (session_dir / "calls.jsonl").read_text().splitlines()
    ]


def _run_open_rows(session_dir) -> list[dict]:
    """The raw run.start (open) rows from runs.jsonl — one per run, each
    carrying the fingerprint including the system-prompt blob ref."""
    rows = [
        json.loads(line)
        for line in (session_dir / "runs.jsonl").read_text().splitlines()
    ]
    return [r for r in rows if r["phase"] == "open"]


def _blob_text(session_dir, ref: str) -> str:
    return (session_dir / "blobs" / ref.removeprefix("sha256:")).read_text()


async def test_create_emits_session_created_and_assemble_writes_artifacts(
    tmp_path,
):
    session = _create(tmp_path, behavior_prompt="you are helpful")
    session_dir = tmp_path / session.session_id

    assert _events(session_dir)[0]["type"] == "session.created"

    _open_run(session)
    session.context.add(Message(role=Role.USER, content="hi"))
    await session.context.assemble()

    assert _events(session_dir)[-1]["type"] == "call.request"
    (record,) = _calls(session_dir)
    assert record["v"] == 3
    # The system prompt is a run-level fact — interned on the run's open row.
    (run_open,) = _run_open_rows(session_dir)
    assert _blob_text(session_dir, run_open["system_prompt"]) == "you are helpful"


def test_load_emits_session_loaded_with_count_and_healing(tmp_path):
    session = _create(tmp_path, behavior_prompt="sys")
    session.context.add(Message(role=Role.USER, content="unanswered"))
    sid = session.session_id

    loaded = _load(sid, tmp_path, behavior_prompt="sys")

    evt = next(e for e in _events(tmp_path / sid) if e["type"] == "session.loaded")
    # The trailing unanswered user message was healed at load — and the
    # trace says so instead of only a logger line.
    assert evt["payload"]["healed"] == ["interrupted_response_marker"]
    assert evt["payload"]["message_count"] == 2
    assert len(loaded.context.store) == 2


async def test_resume_with_edited_prompt_flips_system_prompt_ref(tmp_path):
    """'The agent changed between runs' is a one-line-per-run scan of
    runs.jsonl — the fingerprint now lives at run granularity."""
    session = _create(tmp_path, behavior_prompt="prompt v1")
    _open_run(session)
    session.context.add(Message(role=Role.USER, content="hi"))
    await session.context.assemble()
    _close_run(session)
    session.context.add(Message(role=Role.ASSISTANT, content="hello"))
    sid = session.session_id

    loaded = _load(sid, tmp_path, behavior_prompt="prompt v2")
    _open_run(loaded)
    loaded.context.add(Message(role=Role.USER, content="again"))
    await loaded.context.assemble()
    _close_run(loaded)

    session_dir = tmp_path / sid
    first, second = _run_open_rows(session_dir)
    assert first["system_prompt"] != second["system_prompt"]
    assert _blob_text(session_dir, first["system_prompt"]) == "prompt v1"
    assert _blob_text(session_dir, second["system_prompt"]) == "prompt v2"
    assert _blob_text(session_dir, second["system_prompt"]) == "prompt v2"


def _reconstruct_from_disk(session_dir, call_id: str) -> list[Message]:
    """The audit recipe from the spec, verbatim: session directory only.

    The system prompt is a run-level fact — joined from the call's run open
    row in runs.jsonl, not read off the call record."""
    rec = next(r for r in _calls(session_dir) if r["call_id"] == call_id)
    run = next(r for r in _run_open_rows(session_dir) if r["run_id"] == rec["run_id"])
    system_prompt_ref = run["system_prompt"]
    stored = [
        Message.model_validate_json(line)
        for line in (session_dir / "messages.jsonl").read_text().splitlines()
    ]

    msgs: list[Message] = []
    if system_prompt_ref:
        msgs.append(
            Message(
                role=Role.SYSTEM,
                content=_blob_text(session_dir, system_prompt_ref),
            )
        )
    for start, end in rec["projected"]:
        msgs.extend(stored[start:end])

    offset = 1 if system_prompt_ref else 0
    run, call = rec["injected"]["run"], rec["injected"]["call"]
    if run:
        i = run["anchor"] + offset
        msgs[i] = _merge_into_user(msgs[i], run["text"])
    if call:
        if call["anchor"] is not None:
            i = call["anchor"] + offset
            msgs[i] = _merge_into_user(msgs[i], call["text"])
        else:
            msgs.append(Message(role=Role.USER, content=call["text"]))

    digest = hashlib.sha256(
        "\n".join(m.model_dump_json() for m in msgs).encode()
    ).hexdigest()
    assert f"sha256:{digest}" == rec["assembled_sha256"]  # verified, not trusted
    return msgs


async def test_audit_record_reconstructs_byte_exactly_from_disk(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    session = _create(
        tmp_path,
        behavior_prompt="sys",
        workspace_root=str(ws),
        context_sources=[_RunSource()],
    )
    _open_run(session)
    session.context.add(Message(role=Role.USER, content="what changed?"))

    assembled = await session.context.assemble()

    session_dir = tmp_path / session.session_id
    (record,) = _calls(session_dir)
    rebuilt = _reconstruct_from_disk(session_dir, record["call_id"])
    assert rebuilt == assembled


# ---- context_cls persistence and drift detection ---------------------------


class _SubContext(Context):
    pass


def test_meta_round_trips_context_cls(tmp_path):
    session = _create(tmp_path, context_cls=_SubContext)

    meta = SessionManager(base_dir=tmp_path).read_meta(session.session_id)

    on_disk = json.loads((session.session_dir / "session.json").read_text())
    expected = f"{_SubContext.__module__}.{_SubContext.__qualname__}"
    assert on_disk["context_cls"] == expected
    assert meta.context_cls == expected


def test_default_context_cls_stamps_a_real_class_name(tmp_path):
    """The default has one spelling — never None, never a sentinel."""
    session = _create(tmp_path)

    on_disk = json.loads((session.session_dir / "session.json").read_text())
    assert on_disk["context_cls"] == "minimal_agent.agent.context.Context"


def test_load_session_rejects_a_different_context_cls(tmp_path):
    manager = SessionManager(base_dir=tmp_path)
    created = manager.create_session(
        model=_MODEL, backend=_BACKEND, context_cls=_SubContext
    )

    with pytest.raises(SessionConfigMismatchError) as exc:
        manager.load_session(created.session_id, model=_MODEL, backend=_BACKEND)

    msg = str(exc.value)
    assert "_SubContext" in msg and "minimal_agent.agent.context.Context" in msg


def test_list_sessions_skips_unreadable_meta_but_read_meta_stays_loud(tmp_path):
    manager = SessionManager(base_dir=tmp_path)
    good = manager.create_session(model=_MODEL, backend=_BACKEND)

    # A pre-spec session directory: valid JSON, no context_cls key.
    stale_dir = tmp_path / "stale"
    stale_dir.mkdir()
    stale = json.loads((good.session_dir / "session.json").read_text())
    del stale["context_cls"]
    stale["session_id"] = "stale"
    (stale_dir / "session.json").write_text(json.dumps(stale))

    listed = [s.session_id for s in manager.list_sessions()]
    assert listed == [good.session_id]

    with pytest.raises(KeyError):
        manager.read_meta("stale")
