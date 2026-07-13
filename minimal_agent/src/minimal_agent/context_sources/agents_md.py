"""AGENTS.md — human-authored project instructions injected per run."""

import re
from pathlib import Path
from typing import TYPE_CHECKING

from .base import Placement

if TYPE_CHECKING:
    from ..agent.view import SessionView


class AgentsMdSource:
    """Injects the workspace's AGENTS.md as dynamic context, once per run.

    AGENTS.md is a human-authored, project-level instruction file (the
    cross-tool convention popularized by Codex; analogous to Claude Code's
    CLAUDE.md). Unlike the behavior prompt, it is NOT baked into the system
    prompt — it rides the message channel as RUN-placed context so edits are
    picked up on the next run without rebuilding the session. It is purely
    additive: it augments the behavior prompt, never replaces it.

    Missing or blank file → None (nothing injected).

    Imports: a line that is exactly `@<path>` (after optional leading
    whitespace) is replaced by the contents of `<path>`, resolved relative to
    the workspace root. This lets AGENTS.md pull in a sibling file, e.g.
    `@CLAUDE.md`. Expansion is one level deep (imported files' own `@` lines
    are left literal) and root-scoped; a missing target leaves the line as-is.
    """

    placement = Placement.RUN

    _FILENAME = "AGENTS.md"
    _IMPORT_RE = re.compile(r"^\s*@(?P<path>\S+)\s*$")

    @property
    def name(self) -> str:
        return "agentsMd"

    async def gather(self, session: "SessionView") -> str | None:
        workspace_root = session.workspace_root
        if workspace_root is None:
            return None
        path = workspace_root / self._FILENAME
        try:
            raw = path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return None

        expanded = self._expand_imports(raw, workspace_root)
        return expanded if expanded.strip() else None

    def _expand_imports(self, text: str, workspace_root: Path) -> str:
        out: list[str] = []
        for line in text.splitlines():
            match = self._IMPORT_RE.match(line)
            if match is None:
                out.append(line)
                continue
            imported = self._read_import(match.group("path"), workspace_root)
            # Missing/unreadable target → leave the line literal.
            out.append(imported if imported is not None else line)
        return "\n".join(out)

    def _read_import(self, rel_path: str, workspace_root: Path) -> str | None:
        target = workspace_root / rel_path
        # Root-scoped: never resolve outside the workspace root.
        try:
            target.resolve().relative_to(workspace_root.resolve())
        except ValueError:
            return None
        try:
            return target.read_text(encoding="utf-8").rstrip("\n")
        except (FileNotFoundError, OSError):
            return None
