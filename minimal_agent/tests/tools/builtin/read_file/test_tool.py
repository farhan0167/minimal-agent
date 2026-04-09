"""Integration tests for the ReadFile tool (validate + invoke)."""

from pathlib import Path

from minimal_agent.tools.builtin._filesystem import MAX_FILE_SIZE_BYTES
from minimal_agent.tools.builtin.read_file import ReadFile, ReadFileInput
from minimal_agent.tools.context import ToolContext


def _make_tool(tmp_path: Path) -> tuple[ReadFile, dict[str, float]]:
    ts: dict[str, float] = {}
    return ReadFile(workspace_root=tmp_path, read_timestamps=ts), ts


class TestValidation:
    async def test_valid_read(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        f = tmp_path / "ok.txt"
        f.write_text("hello")
        args = ReadFileInput(file_path=str(f))
        result = await tool.validate(args, ToolContext())
        assert result.ok is True

    async def test_rejects_relative_path(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        args = ReadFileInput(file_path="relative.txt")
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "absolute" in result.message

    async def test_rejects_outside_workspace(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        args = ReadFileInput(file_path="/etc/passwd")
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "outside" in result.message

    async def test_rejects_missing_file(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        missing = tmp_path / "nope.txt"
        args = ReadFileInput(file_path=str(missing))
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "not found" in result.message.lower()

    async def test_rejects_directory(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        d = tmp_path / "subdir"
        d.mkdir()
        args = ReadFileInput(file_path=str(d))
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "Not a file" in result.message

    async def test_rejects_oversized_file_without_offset_limit(
        self, tmp_path: Path
    ):
        tool, _ = _make_tool(tmp_path)
        big = tmp_path / "big.txt"
        big.write_bytes(b"x" * (MAX_FILE_SIZE_BYTES + 1))
        args = ReadFileInput(file_path=str(big))
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "offset/limit" in result.message

    async def test_allows_oversized_file_with_offset_limit(
        self, tmp_path: Path
    ):
        tool, _ = _make_tool(tmp_path)
        big = tmp_path / "big.txt"
        big.write_bytes(b"x" * (MAX_FILE_SIZE_BYTES + 1))
        args = ReadFileInput(file_path=str(big), offset=0, limit=10)
        result = await tool.validate(args, ToolContext())
        assert result.ok is True


class TestInvoke:
    async def test_reads_file_and_records_timestamp(self, tmp_path: Path):
        tool, ts = _make_tool(tmp_path)
        f = tmp_path / "data.txt"
        f.write_text("hello\nworld\n")
        args = ReadFileInput(file_path=str(f))
        result = await tool.invoke(args, ToolContext())

        assert result["total_lines"] == 2
        assert result["num_lines"] == 2
        assert str(f.resolve()) in ts


class TestRenderResult:
    def test_render_result_for_assistant(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        out = {
            "content": "     1\tline1\n     2\tline2",
            "num_lines": 2,
            "total_lines": 10,
            "start_line": 1,
        }
        rendered = tool.render_result_for_assistant(out)
        assert "Lines 1-2 of 10 total" in rendered
        assert "     1\tline1" in rendered
