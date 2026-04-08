"""Integration tests for the Grep tool (validate + invoke with mocked ripgrep)."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from tools.builtin.grep import Grep, GrepInput
from tools.context import ToolContext


def _make_tool(tmp_path: Path) -> Grep:
    return Grep(workspace_root=tmp_path)


class TestValidation:
    async def test_valid_pattern(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        args = GrepInput(pattern="hello")
        result = await tool.validate(args, ToolContext())
        assert result.ok is True

    async def test_rejects_empty_pattern(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        args = GrepInput(pattern="   ")
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "empty" in result.message.lower()

    async def test_rejects_path_outside_workspace(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        args = GrepInput(pattern="x", path="/etc")
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "outside" in result.message

    async def test_rejects_context_lines_in_files_mode(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        args = GrepInput(
            pattern="x",
            output_mode="files_with_matches",
            context_lines=3,
        )
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "context_lines" in result.message

    async def test_allows_relative_path(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        args = GrepInput(pattern="x", path="src")
        result = await tool.validate(args, ToolContext())
        assert result.ok is True


class TestInvoke:
    @patch("tools.builtin.grep.tool.run_ripgrep", new_callable=AsyncMock)
    async def test_files_with_matches(self, mock_rg, tmp_path: Path):
        # Create actual files so sort_by_mtime can stat them
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("hello")
        f2.write_text("hello")

        mock_rg.return_value = (f"{f1}\n{f2}\n", 0)
        tool = _make_tool(tmp_path)
        args = GrepInput(pattern="hello")
        result = await tool.invoke(args, ToolContext())

        assert result["output_mode"] == "files_with_matches"
        assert result["num_files"] == 2
        assert len(result["filenames"]) == 2

    @patch("tools.builtin.grep.tool.run_ripgrep", new_callable=AsyncMock)
    async def test_no_matches(self, mock_rg, tmp_path: Path):
        mock_rg.return_value = ("", 1)
        tool = _make_tool(tmp_path)
        args = GrepInput(pattern="nonexistent")
        result = await tool.invoke(args, ToolContext())

        assert result["num_files"] == 0

    @patch("tools.builtin.grep.tool.run_ripgrep", new_callable=AsyncMock)
    async def test_content_mode(self, mock_rg, tmp_path: Path):
        mock_rg.return_value = ("1:hello world\n2:hello there\n", 0)
        tool = _make_tool(tmp_path)
        args = GrepInput(pattern="hello", output_mode="content")
        result = await tool.invoke(args, ToolContext())

        assert result["output_mode"] == "content"
        assert "hello" in result["content"]

    @patch("tools.builtin.grep.tool.run_ripgrep", new_callable=AsyncMock)
    async def test_count_mode(self, mock_rg, tmp_path: Path):
        mock_rg.return_value = ("a.py:3\nb.py:1\n", 0)
        tool = _make_tool(tmp_path)
        args = GrepInput(pattern="x", output_mode="count")
        result = await tool.invoke(args, ToolContext())

        assert result["output_mode"] == "count"
        assert result["num_files"] == 2


class TestRenderResult:
    def test_files_with_matches_render(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        out = {
            "output_mode": "files_with_matches",
            "content": "",
            "num_files": 2,
            "filenames": ["/a.py", "/b.py"],
            "total_lines": 0,
        }
        rendered = tool.render_result_for_assistant(out)
        assert "Found 2 files" in rendered
        assert "/a.py" in rendered

    def test_no_files_render(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        out = {
            "output_mode": "files_with_matches",
            "content": "",
            "num_files": 0,
            "filenames": [],
            "total_lines": 0,
        }
        rendered = tool.render_result_for_assistant(out)
        assert "No files found" in rendered

    def test_content_render(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        out = {
            "output_mode": "content",
            "content": "1:match here",
            "num_files": 0,
            "filenames": [],
            "total_lines": 1,
        }
        rendered = tool.render_result_for_assistant(out)
        assert "match here" in rendered
