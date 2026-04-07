from agent.message_store import MessageStore
from llm.types import Message, ToolCall


def test_append_and_ordering():
    store = MessageStore()
    m1 = Message(role="user", content="hello")
    m2 = Message(role="assistant", content="hi")
    store.append(m1)
    store.append(m2)

    assert len(store) == 2
    assert store.messages[0] == m1
    assert store.messages[1] == m2


def test_messages_returns_copy():
    store = MessageStore()
    store.append(Message(role="user", content="hello"))

    msgs = store.messages
    msgs.append(Message(role="user", content="injected"))

    assert len(store) == 1


def test_empty_store():
    store = MessageStore()
    assert len(store) == 0
    assert store.messages == []


# --- Persistence tests ---


def test_append_writes_to_disk(tmp_path):
    path = tmp_path / "messages.jsonl"
    store = MessageStore(path=path)

    store.append(Message(role="user", content="hello"))
    store.append(Message(role="assistant", content="world"))

    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    # Verify round-trip: each line is valid JSON that parses back to the message
    assert Message.model_validate_json(lines[0]).content == "hello"
    assert Message.model_validate_json(lines[1]).content == "world"


def test_from_file_round_trip(tmp_path):
    path = tmp_path / "messages.jsonl"
    store = MessageStore(path=path)
    store.append(Message(role="user", content="q"))
    store.append(Message(role="assistant", content="a"))

    loaded = MessageStore.from_file(path)

    assert len(loaded) == 2
    assert loaded.messages[0].content == "q"
    assert loaded.messages[1].content == "a"


def test_from_file_nonexistent_path(tmp_path):
    path = tmp_path / "does_not_exist.jsonl"
    store = MessageStore.from_file(path)

    assert len(store) == 0

    # First append should create the file
    store.append(Message(role="user", content="first"))
    assert path.exists()
    assert len(path.read_text().strip().splitlines()) == 1


def test_append_after_from_file_only_writes_new(tmp_path):
    path = tmp_path / "messages.jsonl"

    # Write two messages
    store = MessageStore(path=path)
    store.append(Message(role="user", content="one"))
    store.append(Message(role="assistant", content="two"))

    # Reload and append one more
    loaded = MessageStore.from_file(path)
    loaded.append(Message(role="user", content="three"))

    # File should have exactly 3 lines, not 5
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 3


def test_in_memory_store_no_files(tmp_path):
    store = MessageStore()  # No path
    store.append(Message(role="user", content="ephemeral"))

    # tmp_path should still be empty
    assert list(tmp_path.iterdir()) == []


def test_from_file_corrupt_last_line(tmp_path):
    path = tmp_path / "messages.jsonl"
    msg = Message(role="user", content="good")
    path.write_text(msg.model_dump_json() + "\n" + "this is not json\n")

    store = MessageStore.from_file(path)

    assert len(store) == 1
    assert store.messages[0].content == "good"


def test_from_file_corrupt_mid_line(tmp_path):
    import pytest

    path = tmp_path / "messages.jsonl"
    good = Message(role="user", content="good")
    path.write_text(
        good.model_dump_json()
        + "\n"
        + "corrupt garbage\n"
        + good.model_dump_json()
        + "\n"
    )

    with pytest.raises(ValueError, match="Corrupt message at line 2"):
        MessageStore.from_file(path)


def test_from_file_orphaned_tool_result(tmp_path):
    import pytest

    path = tmp_path / "messages.jsonl"
    # A tool result with no preceding tool call
    orphan = Message(role="tool", tool_call_id="tc_999", content="result")
    path.write_text(orphan.model_dump_json() + "\n")

    with pytest.raises(ValueError, match="Orphaned tool result"):
        MessageStore.from_file(path)


def test_from_file_valid_tool_pairs(tmp_path):
    path = tmp_path / "messages.jsonl"

    assistant = Message(
        role="assistant",
        content="calling tool",
        tool_calls=[ToolCall(id="tc_1", name="test", arguments={})],
    )
    tool_result = Message(role="tool", tool_call_id="tc_1", content="done")

    path.write_text(
        assistant.model_dump_json() + "\n" + tool_result.model_dump_json() + "\n"
    )

    store = MessageStore.from_file(path)
    assert len(store) == 2
