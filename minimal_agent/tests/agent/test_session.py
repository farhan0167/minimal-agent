import json

import pytest

from agent.session import Session, SessionConfigMismatchError
from llm.types import Message, Usage

_MODEL = "gpt-4o-mini"
_BACKEND = "openai"


def _create(tmp_path, **overrides):
    """Helper to create a session with default model/backend."""
    defaults = dict(
        model=_MODEL,
        backend=_BACKEND,
        base_dir=tmp_path,
    )
    defaults.update(overrides)
    return Session.create(**defaults)


def _load(session_id, tmp_path, **overrides):
    """Helper to load a session with default model/backend."""
    defaults = dict(
        model=_MODEL,
        backend=_BACKEND,
        base_dir=tmp_path,
    )
    defaults.update(overrides)
    return Session.load(session_id, **defaults)


def test_create_makes_directory_and_files(tmp_path):
    session = _create(tmp_path, system_prompt="sys")

    session_dir = tmp_path / session.session_id
    assert session_dir.is_dir()
    assert (session_dir / "session.json").exists()

    meta = json.loads((session_dir / "session.json").read_text())
    assert meta["session_id"] == session.session_id
    assert meta["model"] == _MODEL
    assert meta["backend"] == _BACKEND
    assert meta["usage"] is None


def test_add_message_writes_to_jsonl(tmp_path):
    session = _create(tmp_path, system_prompt="sys")
    session.context.add(Message(role="user", content="hello"))

    messages_path = tmp_path / session.session_id / "messages.jsonl"
    lines = messages_path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert Message.model_validate_json(lines[0]).content == "hello"


def test_load_recovers_messages(tmp_path):
    session = _create(tmp_path, system_prompt="sys")
    session.context.add(Message(role="user", content="q"))
    session.context.add(Message(role="assistant", content="a"))
    sid = session.session_id

    loaded = _load(sid, tmp_path, system_prompt="sys")

    assert len(loaded.context.store) == 2
    assert loaded.context.store.messages[0].content == "q"
    assert loaded.context.store.messages[1].content == "a"


def test_load_uses_provided_system_prompt(tmp_path):
    session = _create(tmp_path, system_prompt="original")
    session.context.add(Message(role="user", content="hi"))
    sid = session.session_id

    loaded = _load(sid, tmp_path, system_prompt="updated")
    msgs = loaded.context.get_messages()

    assert msgs[0].role == "system"
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

    with pytest.raises(
        SessionConfigMismatchError, match="model"
    ):
        _load(sid, tmp_path, model="claude-3-opus")


def test_load_rejects_different_backend(tmp_path):
    session = _create(tmp_path)
    sid = session.session_id

    with pytest.raises(
        SessionConfigMismatchError, match="backend"
    ):
        _load(sid, tmp_path, backend="anthropic")


def test_load_rejects_both_mismatched(tmp_path):
    session = _create(tmp_path)
    sid = session.session_id

    with pytest.raises(SessionConfigMismatchError) as exc_info:
        _load(
            sid, tmp_path, model="other-model", backend="anthropic"
        )
    assert "model" in str(exc_info.value)
    assert "backend" in str(exc_info.value)


def test_update_usage_accumulates(tmp_path):
    session = _create(tmp_path)

    u1 = Usage(
        prompt_tokens=100, completion_tokens=50, total_tokens=150
    )
    session.update_usage(u1)
    assert session.usage == u1

    u2 = Usage(
        prompt_tokens=200, completion_tokens=100, total_tokens=300
    )
    session.update_usage(u2)

    assert session.usage is not None
    assert session.usage.prompt_tokens == 300
    assert session.usage.completion_tokens == 150
    assert session.usage.total_tokens == 450

    # Verify persisted to disk
    meta = json.loads(
        (tmp_path / session.session_id / "session.json").read_text()
    )
    assert meta["usage"]["prompt_tokens"] == 300


def test_update_usage_updates_timestamp(tmp_path):
    session = _create(tmp_path)
    original_updated = session.updated_at

    u = Usage(
        prompt_tokens=10, completion_tokens=5, total_tokens=15
    )
    session.update_usage(u)

    assert session.updated_at >= original_updated


def test_list_sessions_sorted_by_updated_at(tmp_path):
    s1 = _create(tmp_path)
    s1.update_usage(
        Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    )

    s2 = _create(tmp_path)
    s2.update_usage(
        Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    )

    sessions = Session.list_sessions(base_dir=tmp_path)

    assert len(sessions) == 2
    # Most recently updated first
    assert sessions[0].session_id == s2.session_id
    assert sessions[1].session_id == s1.session_id


def test_list_sessions_empty_dir(tmp_path):
    sessions = Session.list_sessions(base_dir=tmp_path)
    assert sessions == []


def test_list_sessions_nonexistent_dir(tmp_path):
    sessions = Session.list_sessions(base_dir=tmp_path / "nope")
    assert sessions == []
