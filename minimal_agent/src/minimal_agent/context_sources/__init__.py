"""Context sources — gather dynamic environment info for the model.

A ContextSource is any object with a `name` property and an async `gather()`
method. The protocol is structural (duck typing) — no inheritance required.
See `base` for the protocol, the `Placement` enum, and resolver helpers; each
built-in source lives in its own module and is re-exported here so callers can
`from minimal_agent.context_sources import ...` without knowing the layout.
"""

from .agents_md import AgentsMdSource
from .base import (
    ContextSource,
    Placement,
    source_placement,
    source_tag,
)
from .directory_tree import DirectoryTreeSource
from .git_status import GitStatusSource
from .skills import SkillsContextSource

__all__ = [
    "AgentsMdSource",
    "ContextSource",
    "DirectoryTreeSource",
    "GitStatusSource",
    "Placement",
    "SkillsContextSource",
    "source_placement",
    "source_tag",
]
