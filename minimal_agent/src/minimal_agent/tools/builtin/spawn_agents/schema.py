"""Input schema for the `spawn_agents` tool.

Kept separate from `tool.py` so tests and sibling tools can import the
schema without dragging in the executor's runtime dependencies.
"""

from pydantic import BaseModel, Field


class SubAgentSpec(BaseModel):
    """Specification for a single sub-agent to spawn."""

    task: str = Field(
        ...,
        description=(
            "A clear, self-contained description of what this sub-agent "
            "should accomplish. The sub-agent sees only this task — include "
            "all necessary context."
        ),
    )
    tools: list[str] | None = Field(
        default=None,
        description=(
            "Tool names this sub-agent may use (e.g. ['read_file', 'grep']). "
            "Null gives it all available tools. Use a restricted set to create "
            "read-only research agents or scoped workers."
        ),
    )
    max_turns: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum agent-loop turns for this sub-agent.",
    )


class SpawnAgentsInput(BaseModel):
    """Spawn one or more sub-agents to work on tasks concurrently.

    Use when a task can be decomposed into independent subtasks that
    benefit from parallel execution. Each sub-agent gets its own context
    and runs to completion before results are collected.
    """

    agents: list[SubAgentSpec] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of sub-agent specifications to run concurrently.",
    )
