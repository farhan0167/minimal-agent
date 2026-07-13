"""Git status — branch, short status, and recent commits, refreshed per run."""

import asyncio
from typing import TYPE_CHECKING

from .base import Placement

if TYPE_CHECKING:
    from ..agent.view import SessionView


class GitStatusSource:
    """Gathers current branch, short status, and recent commits.

    Volatile between runs — the working tree changes as the agent (and the
    user) work — so it rides the message channel, refreshed once per run.
    """

    placement = Placement.RUN

    @property
    def name(self) -> str:
        return "gitStatus"

    async def gather(self, session: "SessionView") -> str | None:
        workspace_root = session.workspace_root
        if workspace_root is None or not (workspace_root / ".git").is_dir():
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
