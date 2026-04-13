"""Tests for context sources."""

from pathlib import Path

from minimal_agent.skills import SkillMeta, SkillSource
from minimal_agent.system_prompt.context_sources import (
    DirectoryTreeSource,
    GitStatusSource,
    SkillsContextSource,
)


class TestGitStatusSource:
    async def test_returns_none_for_non_git_dir(self, tmp_path: Path):
        source = GitStatusSource()
        result = await source.gather(tmp_path)
        assert result is None

    async def test_includes_branch_for_git_repo(self, tmp_path: Path):
        # Initialize a git repo with a commit so branch exists
        import asyncio

        async def run(cmd: list[str]):
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(tmp_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

        await run(["git", "init"])
        await run(["git", "config", "user.email", "test@test.com"])
        await run(["git", "config", "user.name", "Test"])
        (tmp_path / "file.txt").write_text("hello")
        await run(["git", "add", "."])
        await run(["git", "commit", "-m", "init"])

        source = GitStatusSource()
        result = await source.gather(tmp_path)
        assert result is not None
        assert "Branch:" in result

    async def test_name_property(self):
        source = GitStatusSource()
        assert source.name == "gitStatus"


class TestDirectoryTreeSource:
    async def test_empty_directory(self, tmp_path: Path):
        source = DirectoryTreeSource()
        result = await source.gather(tmp_path)
        # Empty dir → no entries → None
        assert result is None

    async def test_lists_files_and_dirs(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("")
        (tmp_path / "README.md").write_text("")

        source = DirectoryTreeSource()
        result = await source.gather(tmp_path)
        assert result is not None
        assert "src/" in result
        assert "main.py" in result
        assert "README.md" in result

    async def test_respects_max_depth(self, tmp_path: Path):
        # Create nested structure deeper than max_depth=1
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "b").mkdir()
        (tmp_path / "a" / "b" / "deep.txt").write_text("")
        (tmp_path / "a" / "shallow.txt").write_text("")

        source = DirectoryTreeSource(max_depth=1)
        result = await source.gather(tmp_path)
        assert result is not None
        assert "a/" in result
        assert "shallow.txt" in result
        # depth=2 content should not appear
        assert "deep.txt" not in result

    async def test_skips_hidden_and_noise_dirs(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("")

        source = DirectoryTreeSource()
        result = await source.gather(tmp_path)
        assert result is not None
        assert ".git" not in result
        assert "__pycache__" not in result
        assert "src/" in result

    async def test_name_property(self):
        source = DirectoryTreeSource()
        assert source.name == "directoryStructure"


class TestSkillsContextSource:
    def _make(
        self, name: str, desc: str = "Does things.", shadowed: bool = False
    ) -> SkillMeta:
        return SkillMeta(
            name=name,
            description=desc,
            path=Path(f"/fake/{name}/SKILL.md"),
            source=SkillSource.PROJECT,
            shadowed_by=SkillSource.USER if shadowed else None,
        )

    async def test_empty_list_returns_none(self, tmp_path: Path):
        source = SkillsContextSource(skills=[])
        assert await source.gather(tmp_path) is None

    async def test_all_shadowed_returns_none(self, tmp_path: Path):
        source = SkillsContextSource(skills=[self._make("c", shadowed=True)])
        assert await source.gather(tmp_path) is None

    async def test_lists_active_skills(self, tmp_path: Path):
        source = SkillsContextSource(
            skills=[
                self._make("commit", "Create commits."),
                self._make("review-pr", "Review PRs."),
            ]
        )
        result = await source.gather(tmp_path)
        assert result is not None
        assert "- commit: Create commits." in result
        assert "- review-pr: Review PRs." in result

    async def test_excludes_shadowed(self, tmp_path: Path):
        source = SkillsContextSource(
            skills=[
                self._make("commit", "Project commit."),
                self._make("commit", "User commit.", shadowed=True),
            ]
        )
        result = await source.gather(tmp_path)
        assert result is not None
        assert "Project commit." in result
        assert "User commit." not in result

    async def test_name_property(self):
        assert SkillsContextSource(skills=[]).name == "availableSkills"


class TestCustomContextSource:
    """A plain object satisfying the ContextSource protocol works."""

    async def test_duck_typed_source(self, tmp_path: Path):
        class MySource:
            @property
            def name(self) -> str:
                return "custom"

            async def gather(self, workspace_root: Path) -> str | None:
                return "custom context data"

        source = MySource()
        assert source.name == "custom"
        result = await source.gather(tmp_path)
        assert result == "custom context data"
