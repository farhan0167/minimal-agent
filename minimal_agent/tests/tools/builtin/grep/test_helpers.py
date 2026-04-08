"""Tests for grep helpers."""

import time
from pathlib import Path

from tools.builtin._filesystem import sort_by_mtime, truncate_text
from tools.builtin.grep.helpers import (
    MAX_RESULTS,
    build_ripgrep_args,
)
from tools.builtin.grep.schema import GrepInput


class TestBuildRipgrepArgs:
    def test_files_with_matches_mode(self):
        inp = GrepInput(pattern="foo")
        args = build_ripgrep_args(inp)
        assert "-l" in args
        assert "-i" in args  # case-insensitive by default
        assert "foo" in args

    def test_content_mode(self):
        inp = GrepInput(pattern="bar", output_mode="content")
        args = build_ripgrep_args(inp)
        assert "-l" not in args
        assert "-n" in args  # line numbers

    def test_count_mode(self):
        inp = GrepInput(pattern="baz", output_mode="count")
        args = build_ripgrep_args(inp)
        assert "-c" in args

    def test_case_sensitive(self):
        inp = GrepInput(pattern="Foo", case_sensitive=True)
        args = build_ripgrep_args(inp)
        assert "-i" not in args

    def test_multiline(self):
        inp = GrepInput(pattern="multi", multiline=True)
        args = build_ripgrep_args(inp)
        assert "-U" in args
        assert "--multiline-dotall" in args

    def test_context_lines_in_content_mode(self):
        inp = GrepInput(
            pattern="ctx", output_mode="content", context_lines=3
        )
        args = build_ripgrep_args(inp)
        idx = args.index("-C")
        assert args[idx + 1] == "3"

    def test_context_lines_ignored_in_files_mode(self):
        inp = GrepInput(
            pattern="ctx",
            output_mode="files_with_matches",
            context_lines=3,
        )
        args = build_ripgrep_args(inp)
        assert "-C" not in args

    def test_glob_filter(self):
        inp = GrepInput(pattern="x", glob="*.py")
        args = build_ripgrep_args(inp)
        idx = args.index("--glob")
        assert args[idx + 1] == "*.py"

    def test_type_filter(self):
        inp = GrepInput(pattern="x", type="py")
        args = build_ripgrep_args(inp)
        idx = args.index("--type")
        assert args[idx + 1] == "py"


class TestSortByMtime:
    def test_sorts_most_recent_first(self, tmp_path: Path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("a")
        time.sleep(0.05)
        b.write_text("b")

        result = sort_by_mtime([str(a), str(b)])
        assert result[0] == str(b)
        assert result[1] == str(a)

    def test_caps_at_max_results(self, tmp_path: Path):
        paths = []
        for i in range(MAX_RESULTS + 10):
            f = tmp_path / f"file{i}.txt"
            f.write_text(str(i))
            paths.append(str(f))

        result = sort_by_mtime(paths, limit=MAX_RESULTS)
        assert len(result) == MAX_RESULTS

    def test_handles_missing_files(self, tmp_path: Path):
        existing = tmp_path / "exists.txt"
        existing.write_text("x")
        result = sort_by_mtime([str(existing), "/nonexistent/file.txt"])
        assert str(existing) in result


class TestTruncateContentOutput:
    def test_under_limit(self):
        text = "short output"
        result, lines = truncate_text(text, max_chars=100)
        assert result == text

    def test_over_limit(self):
        text = "A" * 100 + "\n" + "B" * 100
        result, _ = truncate_text(text, max_chars=50)
        assert result.startswith("A" * 25)
        assert result.endswith("B" * 25)
        assert "truncated" in result

    def test_empty(self):
        result, lines = truncate_text("")
        assert result == ""
        assert lines == 0
