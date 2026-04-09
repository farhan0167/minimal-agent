"""Tests for shared filesystem helpers (is_path_within, MAX_FILE_SIZE_BYTES)."""

from pathlib import Path

from minimal_agent.tools.builtin._filesystem import is_path_within


class TestIsPathWithin:
    def test_child_path(self, tmp_path: Path):
        child = tmp_path / "a" / "b.txt"
        assert is_path_within(child, tmp_path) is True

    def test_root_itself(self, tmp_path: Path):
        assert is_path_within(tmp_path, tmp_path) is True

    def test_outside_path(self, tmp_path: Path):
        outside = tmp_path.parent / "other"
        assert is_path_within(outside, tmp_path) is False

    def test_dotdot_escape(self, tmp_path: Path):
        escape = tmp_path / "a" / ".." / ".." / "etc" / "passwd"
        assert is_path_within(escape, tmp_path) is False

    def test_symlink_escape(self, tmp_path: Path):
        """A symlink pointing outside the root should be rejected."""
        target = tmp_path.parent / "secret.txt"
        target.write_text("secret")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        assert is_path_within(link, tmp_path) is False
