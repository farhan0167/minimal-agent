"""Context sources — gather dynamic environment info for the system prompt.

A ContextSource is any object with a `name` property and an async `gather()`
method. The protocol is structural (duck typing) — no inheritance required.
"""

import asyncio
from pathlib import Path
from typing import Protocol

from ..skills import SkillMeta


class ContextSource(Protocol):
    """A source of dynamic context for the system prompt."""

    @property
    def name(self) -> str:
        """The name used in the <context name="..."> XML tag."""
        ...

    async def gather(self, workspace_root: Path) -> str | None:
        """Gather context. Returns the content string, or None to skip.

        Returning None means this source has nothing to contribute
        (e.g., git status in a non-git directory). The builder skips it.
        """
        ...


class GitStatusSource:
    """Gathers current branch, short status, and recent commits."""

    @property
    def name(self) -> str:
        return "gitStatus"

    async def gather(self, workspace_root: Path) -> str | None:
        if not (workspace_root / ".git").is_dir():
            return None

        async def _run(cmd: list[str]) -> str:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace_root),
            )
            stdout, _ = await proc.communicate()
            return stdout.decode("utf-8", errors="replace").strip()

        branch, status, log = await asyncio.gather(
            _run(["git", "branch", "--show-current"]),
            _run(["git", "status", "--short"]),
            _run(["git", "log", "--oneline", "-n", "5"]),
        )

        # Truncate status if very long
        status_lines = status.split("\n")
        if len(status_lines) > 50:
            remaining = len(status_lines) - 50
            status = "\n".join(status_lines[:50]) + f"\n... ({remaining} more)"

        parts: list[str] = []
        if branch:
            parts.append(f"Branch: {branch}")
        if status:
            parts.append(f"Status:\n{status}")
        if log:
            parts.append(f"Recent commits:\n{log}")

        return "\n\n".join(parts) if parts else None


class DirectoryTreeSource:
    """Gathers a depth-limited file tree of the workspace."""

    def __init__(self, max_depth: int = 3) -> None:
        self._max_depth = max_depth

    @property
    def name(self) -> str:
        return "directoryStructure"

    async def gather(self, workspace_root: Path) -> str | None:
        lines: list[str] = []
        self._walk(workspace_root, "", 0, lines)
        return "\n".join(lines) if lines else None

    def _walk(
        self, path: Path, prefix: str, depth: int, lines: list[str]
    ) -> None:
        if depth > self._max_depth:
            return

        # Skip hidden dirs and common noise
        skip = {
            ".git", "__pycache__", "node_modules",
            ".venv", "venv", ".mypy_cache", ".ruff_cache",
        }

        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        except PermissionError:
            return

        dirs = [e for e in entries if e.is_dir() and e.name not in skip]
        files = [e for e in entries if e.is_file()]

        for d in dirs:
            lines.append(f"{prefix}{d.name}/")
            self._walk(d, prefix + "  ", depth + 1, lines)
        for f in files:
            lines.append(f"{prefix}{f.name}")


class SkillsContextSource:
    """Injects the lightweight skill metadata list into the system prompt.

    Phase 1 of the two-phase skill loading pattern. The model reads this
    list and decides which skill to invoke via the `skill` tool.
    """

    def __init__(self, skills: list[SkillMeta]) -> None:
        self._skills = skills

    @property
    def name(self) -> str:
        return "availableSkills"

    async def gather(self, workspace_root: Path) -> str | None:
        active = [s for s in self._skills if s.shadowed_by is None]
        if not active:
            return None

        lines = [
            "The following skills are available. "
            "Call the `skill` tool with the skill name to load the full instructions:",
            "",
        ]
        for s in active:
            lines.append(f"- {s.name}: {s.description}")
        return "\n".join(lines)
