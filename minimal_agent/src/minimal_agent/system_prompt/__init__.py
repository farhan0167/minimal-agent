"""System prompt module — builds and customizes the agent's system prompt."""

from .builder import build_system_prompt, load_prompt
from .context_sources import (
    ContextSource,
    DirectoryTreeSource,
    GitStatusSource,
    SkillsContextSource,
)

__all__ = [
    "build_system_prompt",
    "load_prompt",
    "ContextSource",
    "DirectoryTreeSource",
    "GitStatusSource",
    "SkillsContextSource",
]
