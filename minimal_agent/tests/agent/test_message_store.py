from minimal_agent.agent.message_store import MessageStore
from minimal_agent.llm.types import Message, Role, ToolCall


def test_append_and_ordering():
    store = MessageStore()
    m1 = Message(role=Role.USER, content="hello")
    m2 = Message(role=Role.ASSISTANT, content="hi")
    store.append(m1)
    store.append(m2)

    assert len(store) == 2
    assert store.messages[0] == m1
    assert store.messages[1] == m2


def test_messages_returns_copy():
    store = MessageStore()
    store.append(Message(role=Role.USER, content="hello"))

    msgs = store.messages
    msgs.append(Message(role=Role.USER, content="injected"))

    assert len(store) == 1


def test_empty_store():
    store = MessageStore()
    assert len(store) == 0
    assert store.messages == []


# --- Persistence tests ---


def test_append_writes_to_disk(tmp_path):
    path = tmp_path / "messages.jsonl"
    store = MessageStore(path=path)

    store.append(Message(role=Role.USER, content="hello"))
    store.append(Message(role=Role.ASSISTANT, content="world"))

    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    # Verify round-trip: each line is valid JSON that parses back to the message
    assert Message.model_validate_json(lines[0]).content == "hello"
    assert Message.model_validate_json(lines[1]).content == "world"


def test_from_file_round_trip(tmp_path):
    path = tmp_path / "messages.jsonl"
    store = MessageStore(path=path)
    store.append(Message(role=Role.USER, content="q"))
    store.append(Message(role=Role.ASSISTANT, content="a"))

    loaded = MessageStore.from_file(path)

    assert len(loaded) == 2
    assert loaded.messages[0].content == "q"
    assert loaded.messages[1].content == "a"


def test_from_file_nonexistent_path(tmp_path):
    path = tmp_path / "does_not_exist.jsonl"
    store = MessageStore.from_file(path)

    assert len(store) == 0

    # First append should create the file
    store.append(Message(role=Role.USER, content="first"))
    assert path.exists()
    assert len(path.read_text().strip().splitlines()) == 1


def test_append_after_from_file_only_writes_new(tmp_path):
    path = tmp_path / "messages.jsonl"

    # Write two messages
    store = MessageStore(path=path)
    store.append(Message(role=Role.USER, content="one"))
    store.append(Message(role=Role.ASSISTANT, content="two"))

    # Reload and append one more
    loaded = MessageStore.from_file(path)
    loaded.append(Message(role=Role.USER, content="three"))

    # File should have exactly 3 lines, not 5
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 3


def test_in_memory_store_no_files(tmp_path):
    store = MessageStore()  # No path
    store.append(Message(role=Role.USER, content="ephemeral"))

    # tmp_path should still be empty
    assert list(tmp_path.iterdir()) == []


def test_from_file_corrupt_last_line(tmp_path):
    path = tmp_path / "messages.jsonl"
    msg = Message(role=Role.USER, content="good")
    path.write_text(msg.model_dump_json() + "\n" + "this is not json\n")

    store = MessageStore.from_file(path)

    assert len(store) == 1
    assert store.messages[0].content == "good"


def test_from_file_corrupt_mid_line(tmp_path):
    import pytest

    path = tmp_path / "messages.jsonl"
    good = Message(role=Role.USER, content="good")
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
    orphan = Message(role=Role.TOOL, tool_call_id="tc_999", content="result")
    path.write_text(orphan.model_dump_json() + "\n")

    with pytest.raises(ValueError, match="Orphaned tool result"):
        MessageStore.from_file(path)


def test_from_file_orphaned_tool_call_at_tail_healed(tmp_path):
    """Interrupted tool calls at the tail get synthetic error results appended."""
    path = tmp_path / "messages.jsonl"

    assistant = Message(
        role=Role.ASSISTANT,
        content="calling tools",
        tool_calls=[
            ToolCall(id="tc_1", name="a", arguments={}),
            ToolCall(id="tc_2", name="b", arguments={}),
            ToolCall(id="tc_3", name="c", arguments={}),
        ],
    )
    result_1 = Message(role=Role.TOOL, tool_call_id="tc_1", content="ok")

    path.write_text(
        assistant.model_dump_json() + "\n" + result_1.model_dump_json() + "\n"
    )

    store = MessageStore.from_file(path)

    # Original 2 messages + 2 synthetic interrupt results
    assert len(store) == 4
    # The two synthetic results should be for tc_2 and tc_3
    synthetic = [m for m in store.messages if "interrupted" in (m.content or "")]
    assert len(synthetic) == 2
    synthetic_ids = {m.tool_call_id for m in synthetic}
    assert synthetic_ids == {"tc_2", "tc_3"}
    # They should suggest retrying
    for m in synthetic:
        assert "you may retry" in m.content

    # Synthetic results should also be persisted to disk
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 4


def test_from_file_orphaned_tool_call_mid_conversation(tmp_path):
    """Orphaned tool calls mid-conversation (not at tail) are corruption."""
    import pytest

    path = tmp_path / "messages.jsonl"

    # Assistant requests tool call, no result follows, then a new user message
    assistant = Message(
        role=Role.ASSISTANT,
        content="calling tool",
        tool_calls=[ToolCall(id="tc_1", name="a", arguments={})],
    )
    user = Message(role=Role.USER, content="moving on")
    # Second assistant with a complete tool pair so tail is clean
    assistant2 = Message(
        role=Role.ASSISTANT,
        content="calling another",
        tool_calls=[ToolCall(id="tc_2", name="b", arguments={})],
    )
    result_2 = Message(role=Role.TOOL, tool_call_id="tc_2", content="ok")

    path.write_text(
        assistant.model_dump_json()
        + "\n"
        + user.model_dump_json()
        + "\n"
        + assistant2.model_dump_json()
        + "\n"
        + result_2.model_dump_json()
        + "\n"
    )

    with pytest.raises(ValueError, match="mid-conversation"):
        MessageStore.from_file(path)


def test_from_file_all_tool_calls_orphaned_at_tail(tmp_path):
    """All tool calls orphaned (none completed) — all get healed."""
    path = tmp_path / "messages.jsonl"

    assistant = Message(
        role=Role.ASSISTANT,
        content="calling tools",
        tool_calls=[
            ToolCall(id="tc_1", name="a", arguments={}),
            ToolCall(id="tc_2", name="b", arguments={}),
        ],
    )

    path.write_text(assistant.model_dump_json() + "\n")

    store = MessageStore.from_file(path)

    assert len(store) == 3  # 1 assistant + 2 synthetic
    synthetic_ids = {
        m.tool_call_id for m in store.messages if m.role == Role.TOOL
    }
    assert synthetic_ids == {"tc_1", "tc_2"}


def test_from_file_valid_tool_pairs(tmp_path):
    path = tmp_path / "messages.jsonl"

    assistant = Message(
        role=Role.ASSISTANT,
        content="calling tool",
        tool_calls=[ToolCall(id="tc_1", name="test", arguments={})],
    )
    tool_result = Message(role=Role.TOOL, tool_call_id="tc_1", content="done")

    path.write_text(
        assistant.model_dump_json() + "\n" + tool_result.model_dump_json() + "\n"
    )

    store = MessageStore.from_file(path)
    assert len(store) == 2
