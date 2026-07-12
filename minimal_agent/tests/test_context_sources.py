"""Tests for context sources."""

import datetime
import platform
from pathlib import Path

import pytest

from minimal_agent.context_sources import (
    AgentsMdSource,
    DirectoryTreeSource,
    EnvSource,
    GitStatusSource,
    Placement,
    SkillsContextSource,
    build_context_blocks,
    source_placement,
    source_tag,
)
from minimal_agent.skills import SkillMeta, SkillSource


class TestAgentsMdSource:
    async def test_returns_none_when_missing(self, tmp_path: Path):
        assert await AgentsMdSource().gather(tmp_path) is None

    async def test_returns_none_when_blank(self, tmp_path: Path):
        (tmp_path / "AGENTS.md").write_text("   \n\n  ")
        assert await AgentsMdSource().gather(tmp_path) is None

    async def test_passthrough_content(self, tmp_path: Path):
        (tmp_path / "AGENTS.md").write_text("Use tabs, not spaces.")
        result = await AgentsMdSource().gather(tmp_path)
        assert result == "Use tabs, not spaces."

    async def test_expands_import_at_line_start(self, tmp_path: Path):
        (tmp_path / "CLAUDE.md").write_text("Project rules here.")
        (tmp_path / "AGENTS.md").write_text("Header\n@CLAUDE.md\nFooter")
        result = await AgentsMdSource().gather(tmp_path)
        assert result == "Header\nProject rules here.\nFooter"

    async def test_missing_import_left_literal(self, tmp_path: Path):
        (tmp_path / "AGENTS.md").write_text("@NOPE.md")
        result = await AgentsMdSource().gather(tmp_path)
        assert result == "@NOPE.md"

    async def test_import_not_at_line_start_ignored(self, tmp_path: Path):
        (tmp_path / "CLAUDE.md").write_text("SHOULD NOT APPEAR")
        (tmp_path / "AGENTS.md").write_text("ping user @CLAUDE.md now")
        result = await AgentsMdSource().gather(tmp_path)
        assert result == "ping user @CLAUDE.md now"

    async def test_import_one_level_only(self, tmp_path: Path):
        # An @-line inside an imported file is NOT recursively expanded.
        (tmp_path / "B.md").write_text("leaf")
        (tmp_path / "CLAUDE.md").write_text("start\n@B.md\nend")
        (tmp_path / "AGENTS.md").write_text("@CLAUDE.md")
        result = await AgentsMdSource().gather(tmp_path)
        assert result == "start\n@B.md\nend"

    async def test_import_outside_root_rejected(self, tmp_path: Path):
        (tmp_path / "AGENTS.md").write_text("@../secret.md")
        result = await AgentsMdSource().gather(tmp_path)
        assert result == "@../secret.md"

    def test_placement_is_run(self):
        assert source_placement(AgentsMdSource()) is Placement.RUN


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


class _BareSource:
    """Only the two protocol members — no placement, no tag."""

    @property
    def name(self) -> str:
        return "bare"

    async def gather(self, workspace_root: Path) -> str | None:
        return "data"


class TestPlacementResolution:
    def test_bare_source_defaults_to_session(self):
        assert source_placement(_BareSource()) is Placement.SESSION

    def test_git_status_is_run(self):
        assert source_placement(GitStatusSource()) is Placement.RUN

    def test_directory_tree_is_session(self):
        assert source_placement(DirectoryTreeSource()) is Placement.SESSION

    def test_skills_source_is_session(self):
        assert source_placement(SkillsContextSource(skills=[])) is (Placement.SESSION)

    def test_plain_string_placement_normalizes(self):
        class StringPlaced(_BareSource):
            placement = "run"

        assert source_placement(StringPlaced()) is Placement.RUN


class TestTagResolution:
    def test_default_tag_is_context(self):
        assert source_tag(_BareSource()) == "context"
        assert source_tag(GitStatusSource()) == "context"

    def test_custom_tag_resolves(self):
        class Reminder(_BareSource):
            tag = "system-reminder"

        assert source_tag(Reminder()) == "system-reminder"


class TestModuleRemoval:
    def test_system_prompt_package_is_gone(self):
        with pytest.raises(ModuleNotFoundError):
            import minimal_agent.system_prompt  # noqa: F401


# ---- EnvSource (the former system_prompt/env.py, as a source) ----------------


class TestEnvSource:
    async def test_contains_workspace_root(self, tmp_path: Path):
        result = await EnvSource().gather(tmp_path)
        assert str(tmp_path) in result

    async def test_contains_platform(self, tmp_path: Path):
        result = await EnvSource().gather(tmp_path)
        assert platform.system().lower() in result

    async def test_contains_date(self, tmp_path: Path):
        result = await EnvSource().gather(tmp_path)
        assert datetime.date.today().isoformat() in result

    async def test_non_git_dir(self, tmp_path: Path):
        result = await EnvSource().gather(tmp_path)
        assert "Is git repo: no" in result

    async def test_git_dir(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        result = await EnvSource().gather(tmp_path)
        assert "Is git repo: yes" in result

    def test_session_placed_with_env_tag(self):
        src = EnvSource()
        assert source_placement(src) is Placement.SESSION
        assert source_tag(src) == "env"

    async def test_golden_block_matches_former_build_env_block(self, tmp_path: Path):
        """The rendered block carries exactly the content build_env_block()
        used to produce, inside the source-tag wrapper."""
        rendered = await build_context_blocks([EnvSource()], tmp_path)
        expected_inner = (
            f"Working directory: {tmp_path}\n"
            f"Platform: {platform.system().lower()}\n"
            f"Date: {datetime.date.today().isoformat()}\n"
            f"Is git repo: no"
        )
        assert rendered == f'<env name="env">\n{expected_inner}\n</env>'


# ---- build_context_blocks (relocated from the deleted builder) ---------------


class _FakeSource:
    def __init__(self, name: str, content: str | None):
        self._name = name
        self._content = content

    @property
    def name(self) -> str:
        return self._name

    async def gather(self, workspace_root: Path) -> str | None:
        return self._content


class TestBuildContextBlocks:
    async def test_empty_sources(self, tmp_path: Path):
        assert await build_context_blocks([], tmp_path) is None

    async def test_all_sources_return_none(self, tmp_path: Path):
        sources = [_FakeSource("a", None), _FakeSource("b", None)]
        assert await build_context_blocks(sources, tmp_path) is None

    async def test_formats_xml_blocks(self, tmp_path: Path):
        sources = [
            _FakeSource("git", "branch: main"),
            _FakeSource("tree", "src/\n  app.py"),
        ]
        result = await build_context_blocks(sources, tmp_path)
        assert result == (
            '<context name="git">\nbranch: main\n</context>\n\n'
            '<context name="tree">\nsrc/\n  app.py\n</context>'
        )

    async def test_skips_none_sources(self, tmp_path: Path):
        sources = [_FakeSource("present", "data"), _FakeSource("absent", None)]
        result = await build_context_blocks(sources, tmp_path)
        assert '<context name="present">' in result
        assert "absent" not in result

    async def test_preamble_prepended_when_given(self, tmp_path: Path):
        result = await build_context_blocks(
            [_FakeSource("x", "content")], tmp_path, preamble="Heads up:"
        )
        assert result.startswith("Heads up:\n\n")

    async def test_custom_tag_wraps_block(self, tmp_path: Path):
        class _TaggedSource(_FakeSource):
            tag = "system-reminder"

        result = await build_context_blocks([_TaggedSource("x", "content")], tmp_path)
        assert result == '<system-reminder name="x">\ncontent\n</system-reminder>'
