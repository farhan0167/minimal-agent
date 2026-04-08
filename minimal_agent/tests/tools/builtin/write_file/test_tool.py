"""Integration tests for the WriteFile tool (validate + invoke)."""

import time
from pathlib import Path

from tools.builtin.write_file import WriteFile, WriteFileInput
from tools.context import ToolContext


def _make_tool(
    tmp_path: Path,
    read_timestamps: dict[str, float] | None = None,
) -> tuple[WriteFile, dict[str, float]]:
    ts = read_timestamps if read_timestamps is not None else {}
    return WriteFile(workspace_root=tmp_path, read_timestamps=ts), ts


class TestValidation:
    async def test_valid_write_new_file(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        target = tmp_path / "new.txt"
        args = WriteFileInput(file_path=str(target), content="hello")
        result = await tool.validate(args, ToolContext())
        assert result.ok is True

    async def test_rejects_relative_path(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        args = WriteFileInput(file_path="relative.txt", content="x")
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "absolute" in result.message

    async def test_rejects_outside_workspace(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        args = WriteFileInput(file_path="/etc/shadow", content="x")
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "outside" in result.message

    async def test_rejects_existing_file_not_read(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        f = tmp_path / "existing.txt"
        f.write_text("old")
        args = WriteFileInput(file_path=str(f), content="new")
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "not been read" in result.message

    async def test_rejects_stale_file(self, tmp_path: Path):
        f = tmp_path / "stale.txt"
        f.write_text("original")
        # Record a read timestamp in the past
        ts: dict[str, float] = {str(f.resolve()): time.time() - 10}
        tool, _ = _make_tool(tmp_path, read_timestamps=ts)
        # Touch the file so mtime > read timestamp
        f.write_text("modified externally")
        args = WriteFileInput(file_path=str(f), content="overwrite")
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "modified since" in result.message

    async def test_allows_existing_file_after_read(self, tmp_path: Path):
        f = tmp_path / "read_first.txt"
        f.write_text("content")
        ts: dict[str, float] = {str(f.resolve()): time.time() + 10}
        tool, _ = _make_tool(tmp_path, read_timestamps=ts)
        args = WriteFileInput(file_path=str(f), content="updated")
        result = await tool.validate(args, ToolContext())
        assert result.ok is True


class TestInvoke:
    async def test_creates_new_file(self, tmp_path: Path):
        tool, ts = _make_tool(tmp_path)
        target = tmp_path / "created.txt"
        args = WriteFileInput(file_path=str(target), content="hello\nworld\n")
        result = await tool.invoke(args, ToolContext())

        assert result["type"] == "create"
        assert result["num_lines"] == 2
        assert target.read_text() == "hello\nworld\n"
        # Timestamp updated after write
        assert str(target.resolve()) in ts

    async def test_successive_writes_without_re_read(self, tmp_path: Path):
        """After invoke updates the timestamp, a second write should validate."""
        tool, ts = _make_tool(tmp_path)
        target = tmp_path / "multi.txt"

        # First write (new file — no read needed)
        args1 = WriteFileInput(file_path=str(target), content="v1")
        await tool.invoke(args1, ToolContext())

        # Second write — should pass validation because invoke updated ts
        args2 = WriteFileInput(file_path=str(target), content="v2")
        result = await tool.validate(args2, ToolContext())
        assert result.ok is True


class TestRenderResult:
    def test_render_create(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        out = {"type": "create", "file_path": "/tmp/new.py", "num_lines": 10}
        assert tool.render_result_for_assistant(out) == "Created /tmp/new.py (10 lines)"

    def test_render_update(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        out = {"type": "update", "file_path": "/tmp/old.py", "num_lines": 5}
        assert tool.render_result_for_assistant(out) == "Updated /tmp/old.py (5 lines)"
