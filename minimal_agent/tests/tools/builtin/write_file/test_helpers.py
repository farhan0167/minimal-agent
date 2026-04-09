"""Tests for write_file helpers (write_text_content)."""

from pathlib import Path

from minimal_agent.tools.builtin.write_file.helpers import write_text_content


class TestWriteTextContent:
    def test_create_new_file(self, tmp_path: Path):
        f = tmp_path / "new.txt"
        result = write_text_content(f, "hello\nworld\n")

        assert result["type"] == "create"
        assert result["num_lines"] == 2
        assert f.read_text(encoding="utf-8") == "hello\nworld\n"

    def test_overwrite_existing_file(self, tmp_path: Path):
        f = tmp_path / "existing.txt"
        f.write_text("old content")
        result = write_text_content(f, "new content")

        assert result["type"] == "update"
        assert f.read_text(encoding="utf-8") == "new content"

    def test_creates_nested_directories(self, tmp_path: Path):
        f = tmp_path / "a" / "b" / "c" / "deep.txt"
        result = write_text_content(f, "deep")

        assert result["type"] == "create"
        assert f.read_text(encoding="utf-8") == "deep"

    def test_empty_content(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        result = write_text_content(f, "")

        assert result["num_lines"] == 0
        assert f.read_text(encoding="utf-8") == ""

    def test_single_line(self, tmp_path: Path):
        f = tmp_path / "one.txt"
        result = write_text_content(f, "single line")

        assert result["num_lines"] == 1

