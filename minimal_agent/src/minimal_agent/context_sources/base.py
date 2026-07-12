"""Context source protocol, placement, resolver helpers, and block formatting.

A ContextSource is any object with a `name` property and an async `gather()`
method. The protocol is structural (duck typing) — no inheritance required.

Each source declares *when* it is gathered and *where* its output lands via
an optional class-level `placement` attribute (see `Placement`). All three
cadences are gathered by `Context`: SESSION sources at its first
`assemble()` (rendered into the system message), RUN and CALL sources
("live sources") on the message channel per call.
"""

import asyncio
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class Placement(StrEnum):
    """When a context source is gathered and where its output lands."""

    SESSION = "session"  # once, at the context's first assemble() → system message
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


async def build_context_blocks(
    sources: list[ContextSource],
    workspace_root: Path,
    *,
    preamble: str | None = None,
) -> str | None:
    """Gather and format one channel's context blocks.

    Calls each source's gather() concurrently. Sources that return None
    are skipped. Returns None if no sources produce content.

    preamble, when given, is prepended to the joined blocks; pass None
    for bare blocks — Context frames its injected blocks itself.
    """
    if not sources:
        return None

    results = await asyncio.gather(*(src.gather(workspace_root) for src in sources))

    blocks: list[str] = []
    for src, content in zip(sources, results, strict=True):
        if content is not None:
            tag = source_tag(src)
            blocks.append(f'<{tag} name="{src.name}">\n{content}\n</{tag}>')

    if not blocks:
        return None

    joined = "\n\n".join(blocks)
    if preamble is None:
        return joined
    return preamble + "\n\n" + joined
