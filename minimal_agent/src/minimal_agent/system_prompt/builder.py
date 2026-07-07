"""Builder — assembles the full system prompt from its parts.

Parts:
1. Behavior prompt (static, from markdown file or string)
2. Environment block (dynamic, computed from workspace)
3. Context blocks (dynamic, from context sources)
"""

import asyncio
from pathlib import Path

from ..context_sources import (
    ContextSource,
    Placement,
    source_placement,
    source_tag,
)
from .env import build_env_block

_DEFAULTS_DIR = Path(__file__).parent / "defaults"
_DEFAULT_BEHAVIOR_PATH = _DEFAULTS_DIR / "behavior.md"

# Prompt-baked context blocks are gathered once, at session creation — the
# preamble says so, so the model re-checks state instead of trusting a
# stale snapshot.
SNAPSHOT_PREAMBLE = (
    "As you answer the user's questions, "
    "you can use the following context.\n"
    "Note: these blocks are a snapshot taken at session start and do not\n"
    "update — use your tools to check current state when it matters:"
)


def load_prompt(prompt: str | Path | None) -> str:
    """Resolve a prompt argument to a string.

    - Path → read the file
    - str → use as-is
    - None → load the default behavior.md
    """
    if prompt is None:
        return _DEFAULT_BEHAVIOR_PATH.read_text()
    if isinstance(prompt, Path):
        return prompt.read_text()
    return prompt


async def build_context_blocks(
    sources: list[ContextSource],
    workspace_root: Path,
    *,
    preamble: str | None = SNAPSHOT_PREAMBLE,
) -> str | None:
    """Gather and format context blocks.

    Calls each source's gather() concurrently. Sources that return None
    are skipped. Returns None if no sources produce content.

    preamble defaults to the snapshot caveat (right for prompt-baked
    blocks); pass None for bare blocks — Context.assemble() frames its
    injected blocks itself.
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


async def build_system_prompt(
    behavior_prompt: str,
    workspace_root: Path,
    context_sources: list[ContextSource] | None = None,
) -> str:
    """Assemble the full system prompt from its parts.

    Returns a single string. All parts are concatenated with
    double-newline separators.

    Only SESSION-placed sources are gathered — RUN/CALL sources belong to
    the message channel (Context.assemble()), never the prompt. The Agent
    already partitions by placement; the filter here keeps direct callers
    correct too.
    """
    parts: list[str] = [behavior_prompt]

    parts.append(build_env_block(workspace_root))

    if context_sources:
        session_sources = [
            s for s in context_sources if source_placement(s) is Placement.SESSION
        ]
        context_block = await build_context_blocks(session_sources, workspace_root)
        if context_block:
            parts.append(context_block)

    return "\n\n".join(parts)
