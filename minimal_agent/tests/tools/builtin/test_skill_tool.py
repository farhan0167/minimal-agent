"""Tests for the `skill` built-in tool."""

from pathlib import Path

import pytest

from minimal_agent.skills import SkillMeta, SkillNotFoundError, SkillSource
from minimal_agent.tools.builtin.skill import SkillInput, SkillTool
from minimal_agent.tools.context import ToolContext


def _make_meta(tmp_path: Path, name: str, body: str = "Body content.") -> SkillMeta:
    skill_dir = tmp_path / name
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        f"---\nname: {name}\ndescription: {name} skill.\n---\n\n{body}\n"
    )
    return SkillMeta(
        name=name,
        description=f"{name} skill.",
        path=skill_file,
        source=SkillSource.PROJECT,
    )


class TestSkillTool:
    async def test_read_only(self):
        tool = SkillTool(skills=[])
        assert tool.is_read_only is True

    async def test_invoke_returns_full_prompt(self, tmp_path: Path):
        meta = _make_meta(tmp_path, "commit", body="# Commit instructions")
        tool = SkillTool(skills=[meta])
        out = await tool.invoke(SkillInput(skill="commit"), ToolContext())

        assert out.skill == "commit"
        assert out.description == "commit skill."
        assert out.args is None
        assert "# Commit instructions" in out.prompt
        assert "name: commit" in out.prompt  # full file including frontmatter

    async def test_invoke_passes_through_args(self, tmp_path: Path):
        meta = _make_meta(tmp_path, "commit")
        tool = SkillTool(skills=[meta])
        out = await tool.invoke(
            SkillInput(skill="commit", args="#123"), ToolContext()
        )
        assert out.args == "#123"

    async def test_invoke_normalizes_name(self, tmp_path: Path):
        meta = _make_meta(tmp_path, "commit")
        tool = SkillTool(skills=[meta])
        out = await tool.invoke(SkillInput(skill="$commit"), ToolContext())
        assert "name: commit" in out.prompt

    async def test_invoke_not_found(self, tmp_path: Path):
        meta = _make_meta(tmp_path, "commit")
        tool = SkillTool(skills=[meta])
        with pytest.raises(SkillNotFoundError):
            await tool.invoke(SkillInput(skill="deploy"), ToolContext())

    async def test_render_result_includes_prompt(self, tmp_path: Path):
        meta = _make_meta(tmp_path, "commit", body="Do the thing.")
        tool = SkillTool(skills=[meta])
        out = await tool.invoke(
            SkillInput(skill="commit", args="x"), ToolContext()
        )
        rendered = tool.render_result_for_assistant(out)
        assert "Skill: commit" in rendered
        assert "Args: x" in rendered
        assert "Do the thing." in rendered

    async def test_as_llm_tool(self):
        llm_tool = SkillTool.as_llm_tool()
        assert llm_tool.name == "skill"
        # Has the two documented fields in its schema.
        schema_str = str(llm_tool.parameters)
        assert "skill" in schema_str
        assert "args" in schema_str
