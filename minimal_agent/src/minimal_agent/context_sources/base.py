"""Context source protocol, placement, and resolver helpers.

A ContextSource is any object with a `name` property and an async `gather()`
method. The protocol is structural (duck typing) — no inheritance required.

Each source declares *when* it is gathered and *where* its output lands via
an optional class-level `placement` attribute (see `Placement`). SESSION
sources are baked into the system prompt at session creation by the
system-prompt builder; RUN and CALL sources ("live sources") bypass the
prompt and are injected into the message list by `Context.assemble()`.
"""

from enum import StrEnum
from pathlib import Path
from typing import Protocol


class Placement(StrEnum):
    """When a context source is gathered and where its output lands."""

    SESSION = "session"  # once at session creation → baked into the system prompt
    RUN = "run"  # once per Agent.run() → merged into the current user message
    CALL = "call"  # before every LLM call → standalone tail carrier


class ContextSource(Protocol):
    """A source of dynamic context. Structural — no inheritance required.

    Optional class attributes (read via getattr, shown with defaults):
        placement: Placement = Placement.SESSION
        tag: str = "context"    # XML wrapper: <{tag} name="{name}">...</{tag}>
    """

    @property
    def name(self) -> str:
        """The name used in the <{tag} name="..."> XML wrapper."""
        ...

    async def gather(self, workspace_root: Path) -> str | None:
        """Gather context. Returns the content string, or None to skip.

        Returning None means this source has nothing to contribute
        (e.g., git status in a non-git directory). The caller skips it.
        """
        ...


def source_placement(src: ContextSource) -> Placement:
    """Resolve a source's placement; absent attribute means SESSION.

    Normalizes through the enum so a duck-typed source declaring a plain
    string (placement = "run") resolves to the same member.
    """
    return Placement(getattr(src, "placement", Placement.SESSION))


def source_tag(src: ContextSource) -> str:
    """Resolve a source's XML wrapper tag; absent attribute means "context"."""
    return getattr(src, "tag", "context")
