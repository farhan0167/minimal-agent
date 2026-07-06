"""Integration tests for the ReadFile tool (validate + invoke)."""

import base64
from pathlib import Path

from minimal_agent.llm.types import ImagePart
from minimal_agent.tools.builtin._filesystem import MAX_FILE_SIZE_BYTES
from minimal_agent.tools.builtin.read_file import ReadFile, ReadFileInput
from minimal_agent.tools.context import ToolContext

# 1x1 transparent PNG.
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


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

    async def test_rejects_oversized_file_without_offset_limit(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        big = tmp_path / "big.txt"
        big.write_bytes(b"x" * (MAX_FILE_SIZE_BYTES + 1))
        args = ReadFileInput(file_path=str(big))
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "offset/limit" in result.message

    async def test_allows_oversized_file_with_offset_limit(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        big = tmp_path / "big.txt"
        big.write_bytes(b"x" * (MAX_FILE_SIZE_BYTES + 1))
        args = ReadFileInput(file_path=str(big), offset=0, limit=10)
        result = await tool.validate(args, ToolContext())
        assert result.ok is True

    async def test_image_bypasses_text_size_guard(self, tmp_path: Path):
        # An image larger than the text limit is fine — the guard is text-only.
        tool, _ = _make_tool(tmp_path)
        img = tmp_path / "big.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * (MAX_FILE_SIZE_BYTES + 1))
        args = ReadFileInput(file_path=str(img))
        result = await tool.validate(args, ToolContext())
        assert result.ok is True


class TestInvoke:
    async def test_reads_file_and_records_timestamp(self, tmp_path: Path):
        tool, ts = _make_tool(tmp_path)
        f = tmp_path / "data.txt"
        f.write_text("hello\nworld\n")
        args = ReadFileInput(file_path=str(f))
        result = await tool.invoke(args, ToolContext())

        assert result["kind"] == "text"
        assert result["total_lines"] == 2
        assert result["num_lines"] == 2
        assert str(f.resolve()) in ts

    async def test_reads_image_as_data_uri(self, tmp_path: Path):
        tool, ts = _make_tool(tmp_path)
        img = tmp_path / "pixel.png"
        img.write_bytes(_PNG_BYTES)
        result = await tool.invoke(ReadFileInput(file_path=str(img)), ToolContext())

        assert result["kind"] == "image"
        assert len(result["data_uris"]) == 1
        assert result["data_uris"][0].startswith("data:image/png;base64,")
        # The data URI round-trips to the original bytes.
        b64 = result["data_uris"][0].split(",", 1)[1]
        assert base64.b64decode(b64) == _PNG_BYTES
        assert str(img.resolve()) in ts

    async def test_reads_pdf_as_one_image_per_page(self, tmp_path: Path, monkeypatch):
        tool, _ = _make_tool(tmp_path)
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        # Stub the rasterizer so the test needs no poppler — return 3 pages.
        # Patch the name as the tool module resolves it (it imported the
        # symbol directly, so patching helpers.* wouldn't take effect).
        import minimal_agent.tools.builtin.read_file.tool as tool_mod

        monkeypatch.setattr(
            tool_mod,
            "pdf_to_data_uris",
            lambda path: [f"data:image/png;base64,PAGE{i}" for i in range(3)],
        )
        result = await tool.invoke(ReadFileInput(file_path=str(pdf)), ToolContext())

        assert result["kind"] == "pdf"
        assert len(result["data_uris"]) == 3


class TestRenderResult:
    def test_render_result_for_assistant(self, tmp_path: Path):
        tool, _ = _make_tool(tmp_path)
        out = {
            "kind": "text",
            "content": "     1\tline1\n     2\tline2",
            "num_lines": 2,
            "total_lines": 10,
            "start_line": 1,
        }
        rendered = tool.render_result_for_assistant(out)
        assert "Lines 1-2 of 10 total" in rendered
        assert "     1\tline1" in rendered

    def test_image_render_is_pointer_and_parts_carry_bytes(self):
        tool, _ = _make_tool(Path("/tmp"))
        out = {
            "kind": "image",
            "path": "/w/pixel.png",
            "data_uris": ["data:image/png;base64,ABC"],
        }
        # Tool-result message is a text pointer, no bytes.
        pointer = tool.render_result_for_assistant(out)
        assert "pixel.png" in pointer
        assert "ABC" not in pointer
        # Bytes ride the relocatable parts.
        parts = tool.render_parts_for_assistant(out)
        assert len(parts) == 1
        assert isinstance(parts[0], ImagePart)
        assert parts[0].image_url.url == "data:image/png;base64,ABC"

    def test_pdf_render_reports_page_count_and_yields_parts(self):
        tool, _ = _make_tool(Path("/tmp"))
        out = {
            "kind": "pdf",
            "path": "/w/doc.pdf",
            "data_uris": ["data:image/png;base64,P1", "data:image/png;base64,P2"],
        }
        pointer = tool.render_result_for_assistant(out)
        assert "2 page(s)" in pointer
        parts = tool.render_parts_for_assistant(out)
        assert len(parts) == 2
        assert all(isinstance(p, ImagePart) for p in parts)

    def test_text_render_yields_no_parts(self):
        tool, _ = _make_tool(Path("/tmp"))
        out = {
            "kind": "text",
            "content": "x",
            "num_lines": 1,
            "total_lines": 1,
            "start_line": 1,
        }
        assert tool.render_parts_for_assistant(out) == []
