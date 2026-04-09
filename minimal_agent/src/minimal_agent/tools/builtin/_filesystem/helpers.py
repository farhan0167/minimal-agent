"""Shared filesystem helpers for builtin tools."""

import os
from pathlib import Path

MAX_FILE_SIZE_BYTES = 256 * 1024  # 256 KB — same ceiling as Claude Code
DEFAULT_TRUNCATE_CHARS = 30_000


def truncate_text(
    content: str, max_chars: int = DEFAULT_TRUNCATE_CHARS
) -> tuple[str, int]:
    """Truncate *content*, keeping the first and last halves.

    Returns ``(truncated_text, total_line_count)``.
    """
    total_lines = content.count("\n") + (1 if content else 0)
    if len(content) <= max_chars:
        return content, total_lines

    half = max_chars // 2
    head = content[:half]
    tail = content[-half:]
    skipped = content[half:-half].count("\n")
    return (
        f"{head}\n\n... [{skipped} lines truncated] ...\n\n{tail}",
        total_lines,
    )


def sort_by_mtime(
    file_paths: list[str], limit: int | None = None
) -> list[str]:
    """Sort file paths by modification time (most recent first).

    When *limit* is given, only the first *limit* results are returned.
    """
    with_mtime: list[tuple[str, float]] = []
    for fp in file_paths:
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            mtime = 0.0
        with_mtime.append((fp, mtime))

    with_mtime.sort(key=lambda x: (-x[1], x[0]))
    sorted_paths = [fp for fp, _ in with_mtime]
    return sorted_paths[:limit] if limit is not None else sorted_paths


def is_path_within(path: Path, root: Path) -> bool:
    """True if `path` is equal to or a descendant of `root`.

    Both paths are resolved before comparison so that `../` segments
    cannot escape the root while appearing contained as a string prefix.
    """
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
