"""Context sources — gather dynamic environment info for the model.

A ContextSource is any object with a `name` property and an async `gather()`
method. The protocol is structural (duck typing) — no inheritance required.
See `base` for the protocol, the `Placement` enum, resolver helpers, and the
block formatter; each built-in source lives in its own module and is
re-exported here so callers can `from minimal_agent.context_sources import
...` without knowing the layout.
"""

from .agents_md import AgentsMdSource
from .base import (
    ContextSource,
    Placement,
    build_context_blocks,
    source_placement,
    source_tag,
)
from .directory_tree import DirectoryTreeSource
from .env_source import EnvSource
from .git_status import GitStatusSource
from .skills import SkillsContextSource

__all__ = [
    "AgentsMdSource",
    "ContextSource",
    "DirectoryTreeSource",
    "EnvSource",
    "GitStatusSource",
    "Placement",
    "SkillsContextSource",
    "build_context_blocks",
    "source_placement",
    "source_tag",
]
