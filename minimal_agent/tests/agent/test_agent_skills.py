"""Tests for Agent integration with the skills system."""

from pathlib import Path
from unittest.mock import AsyncMock

from minimal_agent.agent import Agent, Context


async def _preview_prompt(agent: Agent, root: Path) -> str:
    """The host preview path: a context with the agent's identity,
    gathered explicitly, read via the sync property."""
    ctx = Context(
        behavior_prompt=agent.behavior_prompt,
        context_sources=agent.context_sources,
        workspace_root=root,
    )
    await ctx.ensure_session_gathered()
    return ctx.system_prompt


def _make_llm():
    llm = AsyncMock()
    llm.generate = AsyncMock()
    return llm


def _write_skill(root: Path, name: str, description: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nBody.\n"
    )


async def test_skills_discovered_and_wired(tmp_path: Path):
    skills_dir = tmp_path / ".minimal_agent" / "skills"
    _write_skill(skills_dir, "commit", "Create commits.")

    agent = Agent(llm=_make_llm(), tools=[], workspace_root=tmp_path)

    # SkillTool added to the tool registry
    assert "skill" in agent._tools_by_name
    assert any(t.name == "skill" for t in agent._llm_tools)

    # SkillsContextSource shows up in the system prompt
    prompt = await _preview_prompt(agent, tmp_path)
    assert 'name="availableSkills"' in prompt
    assert "commit: Create commits." in prompt


async def test_no_skills_no_skill_tool(tmp_path: Path):
    # No SKILL.md files → no skill tool registered, no context block.
    agent = Agent(llm=_make_llm(), tools=[], workspace_root=tmp_path)

    assert "skill" not in agent._tools_by_name

    prompt = await _preview_prompt(agent, tmp_path)
    assert "availableSkills" not in prompt


async def test_enable_skills_false(tmp_path: Path):
    skills_dir = tmp_path / ".minimal_agent" / "skills"
    _write_skill(skills_dir, "commit", "Create commits.")

    agent = Agent(
        llm=_make_llm(),
        tools=[],
        workspace_root=tmp_path,
        enable_skills=False,
    )
    assert "skill" not in agent._tools_by_name

    prompt = await _preview_prompt(agent, tmp_path)
    assert "availableSkills" not in prompt


async def test_no_workspace_root_skips_discovery(tmp_path: Path):
    # Without workspace_root, discovery is skipped even if enable_skills=True.
    agent = Agent(llm=_make_llm(), tools=[], enable_skills=True)
    assert "skill" not in agent._tools_by_name
