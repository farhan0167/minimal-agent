"""Tests for the env block builder."""

import datetime
import platform
from pathlib import Path

from minimal_agent.system_prompt.env import build_env_block


class TestBuildEnvBlock:
    def test_contains_workspace_root(self, tmp_path: Path):
        result = build_env_block(tmp_path)
        assert str(tmp_path) in result

    def test_contains_platform(self, tmp_path: Path):
        result = build_env_block(tmp_path)
        assert platform.system().lower() in result

    def test_contains_date(self, tmp_path: Path):
        result = build_env_block(tmp_path)
        assert datetime.date.today().isoformat() in result

    def test_non_git_dir(self, tmp_path: Path):
        result = build_env_block(tmp_path)
        assert "Is git repo: no" in result

    def test_git_dir(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        result = build_env_block(tmp_path)
        assert "Is git repo: yes" in result

    def test_wrapped_in_env_tags(self, tmp_path: Path):
        result = build_env_block(tmp_path)
        assert result.startswith("<env>")
        assert result.endswith("</env>")
