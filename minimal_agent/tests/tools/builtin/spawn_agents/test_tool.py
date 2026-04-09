"""Tests for the `spawn_agents` builtin tool."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel, ValidationError

from minimal_agent.llm.types import GenerateResponse
from minimal_agent.tools.base import BaseTool
from minimal_agent.tools.builtin.spawn_agents import (
    SpawnAgents,
    SpawnAgentsInput,
    SubAgentSpec,
)
from minimal_agent.tools.context import ToolContext

# -- Helpers -----------------------------------------------------------------


class _EmptyInput(BaseModel):
    pass


class _StubTool(BaseTool[_EmptyInput, str]):
    name = "stub_tool"
    input_schema = _EmptyInput

    async def invoke(self, args: _EmptyInput, ctx: ToolContext) -> str:
        return "stub"


class _OtherTool(BaseTool[_EmptyInput, str]):
    name = "other_tool"
    input_schema = _EmptyInput

    async def invoke(self, args: _EmptyInput, ctx: ToolContext) -> str:
        return "other"


def _make_llm(text: str = "done") -> AsyncMock:
    """Mock LLM that returns a single text response with no tool calls."""
    llm = AsyncMock()
    llm.generate = AsyncMock(
        return_value=GenerateResponse(text=text, tool_calls=None)
    )
    return llm


def _make_tool(
    llm: AsyncMock | None = None,
    tools: dict[str, BaseTool] | None = None,
) -> SpawnAgents:
    if llm is None:
        llm = _make_llm()
    if tools is None:
        tools = {"stub_tool": _StubTool(), "other_tool": _OtherTool()}
    return SpawnAgents(
        llm=llm,
        available_tools=tools,
        workspace_root=Path("/tmp/test-workspace"),
    )


# -- Metadata ----------------------------------------------------------------


def test_metadata():
    assert SpawnAgents.name == "spawn_agents"
    assert SpawnAgents.input_schema is SpawnAgentsInput


def test_as_llm_tool_projects_schema():
    tool = _make_tool()
    wire = tool.as_llm_tool()
    assert wire.name == "spawn_agents"
    assert "agents" in wire.parameters.get("properties", {})


# -- Tool resolution ---------------------------------------------------------


def test_resolve_tools_all_excludes_self():
    """When tools=None, sub-agent gets everything except spawn_agents."""
    spawn = _make_tool()
    # Add spawn_agents itself to the available_tools dict
    spawn._available_tools["spawn_agents"] = spawn

    resolved = spawn._resolve_tools(None)
    names = {t.name for t in resolved}
    assert "stub_tool" in names
    assert "other_tool" in names
    assert "spawn_agents" not in names


def test_resolve_tools_explicit_subset():
    """When tools=['stub_tool'], only that tool is resolved."""
    spawn = _make_tool()
    resolved = spawn._resolve_tools(["stub_tool"])
    assert len(resolved) == 1
    assert resolved[0].name == "stub_tool"


def test_resolve_tools_unknown_names_skipped():
    """Unknown tool names are silently ignored."""
    spawn = _make_tool()
    resolved = spawn._resolve_tools(["stub_tool", "nonexistent"])
    assert len(resolved) == 1
    assert resolved[0].name == "stub_tool"


def test_resolve_tools_explicit_spawn_agents_excluded():
    """Even if explicitly requested, spawn_agents is excluded."""
    spawn = _make_tool()
    spawn._available_tools["spawn_agents"] = spawn
    resolved = spawn._resolve_tools(["spawn_agents", "stub_tool"])
    names = {t.name for t in resolved}
    assert "spawn_agents" not in names
    assert "stub_tool" in names


# -- Sub-agent execution -----------------------------------------------------


async def test_single_agent_returns_result():
    """A single sub-agent runs and its final answer is returned."""
    llm = _make_llm(text="The answer is 42.")
    tool = _make_tool(llm=llm)

    args = SpawnAgentsInput(
        agents=[SubAgentSpec(task="What is 6 * 7?")]
    )
    result = await tool.invoke(args, ToolContext())

    assert "The answer is 42." in result
    assert "[Sub-agent 1:" in result


async def test_multiple_agents_run_concurrently():
    """Multiple sub-agents all produce results."""
    call_count = 0

    async def mock_generate(**kwargs):
        nonlocal call_count
        call_count += 1
        return GenerateResponse(
            text=f"result-{call_count}", tool_calls=None
        )

    llm = AsyncMock()
    llm.generate = AsyncMock(side_effect=mock_generate)
    tool = _make_tool(llm=llm)

    args = SpawnAgentsInput(
        agents=[
            SubAgentSpec(task="task A"),
            SubAgentSpec(task="task B"),
            SubAgentSpec(task="task C"),
        ]
    )
    result = await tool.invoke(args, ToolContext())

    assert "[Sub-agent 1:" in result
    assert "[Sub-agent 2:" in result
    assert "[Sub-agent 3:" in result
    # Each agent makes at least one LLM call
    assert call_count >= 3


async def test_agent_with_no_output():
    """Sub-agent that produces no text content gets a fallback message."""
    llm = AsyncMock()
    llm.generate = AsyncMock(
        return_value=GenerateResponse(text="", tool_calls=None)
    )
    tool = _make_tool(llm=llm)

    args = SpawnAgentsInput(
        agents=[SubAgentSpec(task="do nothing")]
    )
    result = await tool.invoke(args, ToolContext())

    assert "(sub-agent produced no output)" in result


async def test_agent_error_captured_not_raised():
    """If a sub-agent's LLM call raises, the error is captured in the result."""
    llm = AsyncMock()
    llm.generate = AsyncMock(side_effect=RuntimeError("LLM is down"))
    tool = _make_tool(llm=llm)

    args = SpawnAgentsInput(
        agents=[SubAgentSpec(task="will fail")]
    )
    result = await tool.invoke(args, ToolContext())

    assert "ERROR" in result
    assert "RuntimeError" in result
    assert "LLM is down" in result


async def test_max_turns_forwarded_to_sub_agent():
    """The max_turns from the spec is respected by the sub-agent."""
    from minimal_agent.llm.types import ToolCall

    responses = [
        GenerateResponse(
            text="calling",
            tool_calls=[ToolCall(id=f"tc_{i}", name="stub_tool", arguments={})],
        )
        for i in range(20)
    ]

    llm = AsyncMock()
    llm.generate = AsyncMock(side_effect=responses)
    tool = _make_tool(llm=llm)

    args = SpawnAgentsInput(
        agents=[SubAgentSpec(task="loop forever", max_turns=2)]
    )
    await tool.invoke(args, ToolContext())

    # Sub-agent should have called generate exactly 2 times (max_turns=2)
    assert llm.generate.call_count == 2


async def test_tool_scoping_passed_to_sub_agent():
    """When tools are specified, the sub-agent only gets those tools."""
    llm = _make_llm(text="used only stub_tool")
    tool = _make_tool(llm=llm)

    args = SpawnAgentsInput(
        agents=[SubAgentSpec(task="search", tools=["stub_tool"])]
    )
    result = await tool.invoke(args, ToolContext())

    assert "used only stub_tool" in result


# -- Schema validation ------------------------------------------------------


def test_schema_rejects_empty_agents_list():
    """At least one agent is required."""
    with pytest.raises(ValidationError, match="agents"):
        SpawnAgentsInput(agents=[])


def test_schema_rejects_too_many_agents():
    """No more than 10 agents allowed."""
    specs = [SubAgentSpec(task=f"task {i}") for i in range(11)]
    with pytest.raises(ValidationError, match="agents"):
        SpawnAgentsInput(agents=specs)


def test_schema_max_turns_bounds():
    """max_turns must be between 1 and 20."""
    with pytest.raises(ValidationError):
        SubAgentSpec(task="x", max_turns=0)

    with pytest.raises(ValidationError):
        SubAgentSpec(task="x", max_turns=21)

    # Valid bounds
    assert SubAgentSpec(task="x", max_turns=1).max_turns == 1
    assert SubAgentSpec(task="x", max_turns=20).max_turns == 20
