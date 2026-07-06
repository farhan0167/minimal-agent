"""System prompt module — builds and customizes the agent's system prompt."""

# Context sources moved to minimal_agent.context_sources (they now feed the
# message channel too, not just the prompt). Re-exported here so existing
# imports keep working; new code should import from the new home.
from ..context_sources import (
    AgentsMdSource,
    ContextSource,
    DirectoryTreeSource,
    GitStatusSource,
    SkillsContextSource,
)
from .builder import build_system_prompt, load_prompt

__all__ = [
    "build_system_prompt",
    "load_prompt",
    "AgentsMdSource",
    "ContextSource",
    "DirectoryTreeSource",
    "GitStatusSource",
    "SkillsContextSource",
]
