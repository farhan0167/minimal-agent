"""Integration tests for the Glob tool."""

from pathlib import Path

from minimal_agent.tools.builtin.glob import Glob, GlobInput
from minimal_agent.tools.context import ToolContext


def _make_tool(tmp_path: Path) -> Glob:
    return Glob(workspace_root=tmp_path)


class TestValidation:
    async def test_valid_pattern(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        args = GlobInput(pattern="**/*.py")
        result = await tool.validate(args, ToolContext())
        assert result.ok is True

    async def test_rejects_empty_pattern(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        args = GlobInput(pattern="  ")
        result = await tool.validate(args, ToolContext())
        assert result.ok is False

    async def test_rejects_path_outside_workspace(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        args = GlobInput(pattern="*", path="/etc")
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "outside" in result.message


class TestInvoke:
    async def test_finds_matching_files(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.py").write_text("x")
        (tmp_path / "c.txt").write_text("x")

        tool = _make_tool(tmp_path)
        args = GlobInput(pattern="*.py")
        result = await tool.invoke(args, ToolContext())

        assert result["num_files"] == 2
        names = [Path(f).name for f in result["filenames"]]
        assert "a.py" in names
        assert "b.py" in names
        assert "c.txt" not in names

    async def test_recursive_glob(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").write_text("x")
        (tmp_path / "top.py").write_text("x")

        tool = _make_tool(tmp_path)
        args = GlobInput(pattern="**/*.py")
        result = await tool.invoke(args, ToolContext())

        assert result["num_files"] == 2

    async def test_no_matches(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        args = GlobInput(pattern="*.rs")
        result = await tool.invoke(args, ToolContext())

        assert result["num_files"] == 0

    async def test_sorted_by_mtime(self, tmp_path: Path):
        import time

        a = tmp_path / "a.py"
        a.write_text("first")
        time.sleep(0.05)
        b = tmp_path / "b.py"
        b.write_text("second")

        tool = _make_tool(tmp_path)
        args = GlobInput(pattern="*.py")
        result = await tool.invoke(args, ToolContext())

        # Most recent first
        assert Path(result["filenames"][0]).name == "b.py"

    async def test_truncation_at_max_results(self, tmp_path: Path):
        for i in range(110):
            (tmp_path / f"file{i:03d}.txt").write_text("x")

        tool = _make_tool(tmp_path)
        args = GlobInput(pattern="*.txt")
        result = await tool.invoke(args, ToolContext())

        assert result["num_files"] == 110
        assert len(result["filenames"]) == 100
        assert result["truncated"] is True

    async def test_relative_path(self, tmp_path: Path):
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "main.py").write_text("x")

        tool = _make_tool(tmp_path)
        args = GlobInput(pattern="*.py", path="src")
        result = await tool.invoke(args, ToolContext())

        assert result["num_files"] == 1


class TestRenderResult:
    def test_no_files(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        out = {"filenames": [], "num_files": 0, "truncated": False}
        assert tool.render_result_for_assistant(out) == "No files found"

    def test_with_files(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        out = {
            "filenames": ["/a.py", "/b.py"],
            "num_files": 2,
            "truncated": False,
        }
        rendered = tool.render_result_for_assistant(out)
        assert "/a.py" in rendered
        assert "/b.py" in rendered

    def test_truncated(self, tmp_path: Path):
        tool = _make_tool(tmp_path)
        out = {
            "filenames": ["/a.py"],
            "num_files": 101,
            "truncated": True,
        }
        rendered = tool.render_result_for_assistant(out)
        assert "truncated" in rendered.lower()
