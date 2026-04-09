"""Tests for the ``edit_file`` builtin tool."""

import time
from pathlib import Path

from minimal_agent.tools import ToolContext
from minimal_agent.tools.builtin.edit_file import EditFile, EditFileInput
from minimal_agent.tools.results import ValidationErr, ValidationOk


def _make_tool(tmp_path: Path) -> tuple[EditFile, dict[str, float]]:
    ts: dict[str, float] = {}
    tool = EditFile(workspace_root=tmp_path, read_timestamps=ts)
    return tool, ts


def _write_and_mark_read(
    path: Path, content: str, ts: dict[str, float]
) -> None:
    """Write a file and mark it as read (simulating a prior read_file call)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    ts[str(path.resolve())] = path.stat().st_mtime


# -- Metadata ----------------------------------------------------------------


def test_metadata():
    assert EditFile.name == "edit_file"
    assert EditFile.is_read_only is False
    assert EditFile.input_schema is EditFileInput


def test_as_llm_tool_schema():
    wire = EditFile.as_llm_tool()
    assert wire.name == "edit_file"
    assert "find-and-replace" in wire.description.lower()
    assert set(wire.parameters["required"]) == {"file_path", "old_string", "new_string"}


# -- Validation --------------------------------------------------------------


async def test_validate_rejects_relative_path(tmp_path):
    tool, _ = _make_tool(tmp_path)
    args = EditFileInput(file_path="relative.py", old_string="a", new_string="b")
    result = await tool.validate(args, ToolContext())
    assert isinstance(result, ValidationErr)
    assert "absolute" in result.message


async def test_validate_rejects_outside_workspace(tmp_path):
    tool, _ = _make_tool(tmp_path)
    args = EditFileInput(file_path="/etc/passwd", old_string="a", new_string="b")
    result = await tool.validate(args, ToolContext())
    assert isinstance(result, ValidationErr)
    assert "outside" in result.message


async def test_validate_rejects_nonexistent_file(tmp_path):
    tool, _ = _make_tool(tmp_path)
    path = str(tmp_path / "nope.py")
    args = EditFileInput(file_path=path, old_string="a", new_string="b")
    result = await tool.validate(args, ToolContext())
    assert isinstance(result, ValidationErr)
    assert "not found" in result.message.lower()


async def test_validate_rejects_unread_file(tmp_path):
    tool, _ = _make_tool(tmp_path)
    path = tmp_path / "file.py"
    path.write_text("hello", encoding="utf-8")
    args = EditFileInput(file_path=str(path), old_string="hello", new_string="world")
    result = await tool.validate(args, ToolContext())
    assert isinstance(result, ValidationErr)
    assert "not been read" in result.message


async def test_validate_rejects_stale_file(tmp_path):
    tool, ts = _make_tool(tmp_path)
    path = tmp_path / "file.py"
    path.write_text("hello", encoding="utf-8")
    # Mark as read in the past
    ts[str(path.resolve())] = path.stat().st_mtime - 10
    # Touch the file to make it newer
    time.sleep(0.01)
    path.write_text("hello modified", encoding="utf-8")

    args = EditFileInput(file_path=str(path), old_string="hello", new_string="world")
    result = await tool.validate(args, ToolContext())
    assert isinstance(result, ValidationErr)
    assert "modified since" in result.message


async def test_validate_rejects_identical_strings(tmp_path):
    tool, ts = _make_tool(tmp_path)
    path = tmp_path / "file.py"
    _write_and_mark_read(path, "hello world", ts)

    args = EditFileInput(file_path=str(path), old_string="hello", new_string="hello")
    result = await tool.validate(args, ToolContext())
    assert isinstance(result, ValidationErr)
    assert "identical" in result.message


async def test_validate_rejects_old_string_not_found(tmp_path):
    tool, ts = _make_tool(tmp_path)
    path = tmp_path / "file.py"
    _write_and_mark_read(path, "hello world", ts)

    args = EditFileInput(file_path=str(path), old_string="xyz", new_string="abc")
    result = await tool.validate(args, ToolContext())
    assert isinstance(result, ValidationErr)
    assert "not found" in result.message


async def test_validate_rejects_ambiguous_match(tmp_path):
    tool, ts = _make_tool(tmp_path)
    path = tmp_path / "file.py"
    _write_and_mark_read(path, "foo bar foo", ts)

    args = EditFileInput(file_path=str(path), old_string="foo", new_string="baz")
    result = await tool.validate(args, ToolContext())
    assert isinstance(result, ValidationErr)
    assert "2 times" in result.message


async def test_validate_accepts_valid_edit(tmp_path):
    tool, ts = _make_tool(tmp_path)
    path = tmp_path / "file.py"
    _write_and_mark_read(path, "hello world", ts)

    args = EditFileInput(file_path=str(path), old_string="hello", new_string="goodbye")
    result = await tool.validate(args, ToolContext())
    assert isinstance(result, ValidationOk)


# -- Invoke ------------------------------------------------------------------


async def test_invoke_replaces_content(tmp_path):
    tool, ts = _make_tool(tmp_path)
    path = tmp_path / "file.py"
    _write_and_mark_read(path, "def foo():\n    return 1\n", ts)

    args = EditFileInput(
        file_path=str(path),
        old_string="return 1",
        new_string="return 42",
    )
    result = await tool.invoke(args, ToolContext())

    assert path.read_text() == "def foo():\n    return 42\n"
    assert result["file_path"] == str(path)
    assert "return 42" in result["preview"]


async def test_invoke_updates_read_timestamp(tmp_path):
    tool, ts = _make_tool(tmp_path)
    path = tmp_path / "file.py"
    _write_and_mark_read(path, "aaa", ts)
    old_ts = ts[str(path.resolve())]

    args = EditFileInput(file_path=str(path), old_string="aaa", new_string="bbb")
    await tool.invoke(args, ToolContext())

    new_ts = ts[str(path.resolve())]
    assert new_ts >= old_ts


async def test_invoke_multiline_edit(tmp_path):
    tool, ts = _make_tool(tmp_path)
    path = tmp_path / "file.py"
    original = "line1\nline2\nline3\nline4\n"
    _write_and_mark_read(path, original, ts)

    args = EditFileInput(
        file_path=str(path),
        old_string="line2\nline3",
        new_string="replaced2\nreplaced3\nextra",
    )
    await tool.invoke(args, ToolContext())

    assert path.read_text() == "line1\nreplaced2\nreplaced3\nextra\nline4\n"


# -- Permissions -------------------------------------------------------------


def test_needs_permission():
    tool, _ = _make_tool(Path("/tmp"))
    args = EditFileInput(file_path="/tmp/x.py", old_string="a", new_string="b")
    assert tool.needs_permission(args) is True


def test_permission_description():
    tool, _ = _make_tool(Path("/tmp"))
    args = EditFileInput(
        file_path="/tmp/x.py",
        old_string="one\ntwo\nthree",
        new_string="replaced",
    )
    desc = tool.permission_description(args)
    assert "Edit /tmp/x.py" in desc
    assert "3 lines" in desc
    assert "with 1" in desc


# -- Render ------------------------------------------------------------------


def test_render_result():
    tool, _ = _make_tool(Path("/tmp"))
    out = {"file_path": "/tmp/x.py", "preview": "     1\thello"}
    rendered = tool.render_result_for_assistant(out)
    assert "Edited /tmp/x.py" in rendered
    assert "hello" in rendered
