"""Builder — assembles the full system prompt from its parts.

Parts:
1. Behavior prompt (static, from markdown file or string)
2. Environment block (dynamic, computed from workspace)
3. Context blocks (dynamic, from context sources)
"""

import asyncio
from pathlib import Path

from .context_sources import ContextSource
from .env import build_env_block

_DEFAULTS_DIR = Path(__file__).parent / "defaults"
_DEFAULT_BEHAVIOR_PATH = _DEFAULTS_DIR / "behavior.md"


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
) -> str | None:
    """Gather and format context blocks.

    Calls each source's gather() concurrently. Sources that return None
    are skipped. Returns None if no sources produce content.
    """
    if not sources:
        return None

    results = await asyncio.gather(
        *(src.gather(workspace_root) for src in sources)
    )

    blocks: list[str] = []
    for src, content in zip(sources, results, strict=True):
        if content is not None:
            blocks.append(f'<context name="{src.name}">\n{content}\n</context>')

    if not blocks:
        return None

    preamble = (
        "As you answer the user's questions, "
        "you can use the following context:"
    )
    return preamble + "\n\n" + "\n\n".join(blocks)


async def build_system_prompt(
    behavior_prompt: str,
    workspace_root: Path,
    context_sources: list[ContextSource] | None = None,
) -> str:
    """Assemble the full system prompt from its parts.

    Returns a single string. All parts are concatenated with
    double-newline separators.
    """
    parts: list[str] = [behavior_prompt]

    parts.append(build_env_block(workspace_root))

    if context_sources:
        context_block = await build_context_blocks(
            context_sources, workspace_root
        )
        if context_block:
            parts.append(context_block)

    return "\n\n".join(parts)
