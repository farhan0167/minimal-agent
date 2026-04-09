"""Tests for read_file helpers (read_text_content)."""

from pathlib import Path

from minimal_agent.tools.builtin.read_file.helpers import read_text_content


class TestReadTextContent:
    def test_full_read(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")

        result = read_text_content(f)

        assert result["total_lines"] == 3
        assert result["num_lines"] == 3
        assert result["start_line"] == 1
        assert "     1\tline1" in result["content"]
        assert "     3\tline3" in result["content"]

    def test_offset_only(self, tmp_path: Path):
        f = tmp_path / "f.txt"
        f.write_text("a\nb\nc\nd\n", encoding="utf-8")

        result = read_text_content(f, offset=2)

        assert result["total_lines"] == 4
        assert result["num_lines"] == 2
        assert result["start_line"] == 3  # 1-indexed
        assert "     3\tc" in result["content"]
        assert "     4\td" in result["content"]

    def test_limit_only(self, tmp_path: Path):
        f = tmp_path / "f.txt"
        f.write_text("a\nb\nc\nd\n", encoding="utf-8")

        result = read_text_content(f, limit=2)

        assert result["num_lines"] == 2
        assert result["start_line"] == 1
        assert "     1\ta" in result["content"]
        assert "     2\tb" in result["content"]
        assert "c" not in result["content"]

    def test_offset_and_limit(self, tmp_path: Path):
        f = tmp_path / "f.txt"
        f.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

        result = read_text_content(f, offset=1, limit=2)

        assert result["num_lines"] == 2
        assert result["start_line"] == 2
        assert "     2\tb" in result["content"]
        assert "     3\tc" in result["content"]

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")

        result = read_text_content(f)

        assert result["total_lines"] == 0
        assert result["num_lines"] == 0
        assert result["content"] == ""

    def test_line_numbers_are_one_indexed(self, tmp_path: Path):
        f = tmp_path / "f.txt"
        f.write_text("only\n", encoding="utf-8")

        result = read_text_content(f)

        assert result["start_line"] == 1
        assert result["content"].startswith("     1\t")

