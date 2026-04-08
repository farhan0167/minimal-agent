"""Tests for the system prompt builder."""

from pathlib import Path

from system_prompt.builder import (
    build_context_blocks,
    build_system_prompt,
    load_prompt,
)


class _FakeSource:
    """A minimal context source for testing."""

    def __init__(self, name: str, content: str | None):
        self._name = name
        self._content = content

    @property
    def name(self) -> str:
        return self._name

    async def gather(self, workspace_root: Path) -> str | None:
        return self._content


class TestLoadPrompt:
    def test_none_loads_default(self):
        result = load_prompt(None)
        # The default prompt should contain recognizable content
        assert "software engineering" in result.lower() or "tool" in result.lower()
        assert len(result) > 50

    def test_string_returns_as_is(self):
        result = load_prompt("You are a test agent.")
        assert result == "You are a test agent."

    def test_path_reads_file(self, tmp_path: Path):
        prompt_file = tmp_path / "my_prompt.md"
        prompt_file.write_text("Custom prompt content.")
        result = load_prompt(prompt_file)
        assert result == "Custom prompt content."


class TestBuildContextBlocks:
    async def test_empty_sources(self, tmp_path: Path):
        result = await build_context_blocks([], tmp_path)
        assert result is None

    async def test_all_sources_return_none(self, tmp_path: Path):
        sources = [_FakeSource("a", None), _FakeSource("b", None)]
        result = await build_context_blocks(sources, tmp_path)
        assert result is None

    async def test_formats_xml_blocks(self, tmp_path: Path):
        sources = [
            _FakeSource("git", "branch: main"),
            _FakeSource("tree", "src/\n  app.py"),
        ]
        result = await build_context_blocks(sources, tmp_path)
        assert result is not None
        assert '<context name="git">' in result
        assert "branch: main" in result
        assert '<context name="tree">' in result
        assert "src/" in result

    async def test_skips_none_sources(self, tmp_path: Path):
        sources = [
            _FakeSource("present", "data"),
            _FakeSource("absent", None),
        ]
        result = await build_context_blocks(sources, tmp_path)
        assert result is not None
        assert '<context name="present">' in result
        assert "absent" not in result

    async def test_includes_preamble(self, tmp_path: Path):
        sources = [_FakeSource("x", "content")]
        result = await build_context_blocks(sources, tmp_path)
        assert result is not None
        assert "you can use the following context" in result


class TestBuildSystemPrompt:
    async def test_behavior_plus_env(self, tmp_path: Path):
        result = await build_system_prompt(
            behavior_prompt="You are a test agent.",
            workspace_root=tmp_path,
        )
        assert result.startswith("You are a test agent.")
        assert "<env>" in result
        assert str(tmp_path) in result

    async def test_with_context_sources(self, tmp_path: Path):
        sources = [_FakeSource("info", "some info")]
        result = await build_system_prompt(
            behavior_prompt="Test.",
            workspace_root=tmp_path,
            context_sources=sources,
        )
        assert '<context name="info">' in result
        assert "some info" in result

    async def test_no_context_block_when_all_none(self, tmp_path: Path):
        sources = [_FakeSource("empty", None)]
        result = await build_system_prompt(
            behavior_prompt="Test.",
            workspace_root=tmp_path,
            context_sources=sources,
        )
        assert "context" not in result.lower() or "<env>" in result
        # More precise: no <context> tags
        assert '<context name="' not in result

    async def test_default_prompt_loaded(self, tmp_path: Path):
        default_prompt = load_prompt(None)
        result = await build_system_prompt(
            behavior_prompt=default_prompt,
            workspace_root=tmp_path,
        )
        assert "tool" in result.lower()
