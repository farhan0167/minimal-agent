"""Directory tree — a depth-limited file listing of the workspace."""

from pathlib import Path


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

    def _walk(self, path: Path, prefix: str, depth: int, lines: list[str]) -> None:
        if depth > self._max_depth:
            return

        # Skip hidden dirs and common noise
        skip = {
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            ".mypy_cache",
            ".ruff_cache",
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
