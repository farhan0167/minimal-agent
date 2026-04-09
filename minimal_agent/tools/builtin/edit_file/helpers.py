"""Helpers for the ``edit_file`` tool."""

_CONTEXT_LINES = 4


def find_match_count(content: str, old_string: str) -> int:
    """Return the number of non-overlapping occurrences of *old_string*."""
    return content.count(old_string)


def apply_edit(content: str, old_string: str, new_string: str) -> str:
    """Replace the single occurrence of *old_string* with *new_string*."""
    return content.replace(old_string, new_string, 1)


def build_preview(
    content: str,
    new_string: str,
    *,
    context_lines: int = _CONTEXT_LINES,
) -> str:
    """Build a numbered snippet showing *new_string* in its surrounding context.

    Returns a ``cat -n`` style preview centered on the replacement.
    """
    lines = content.splitlines()

    # Find the line range that contains the replacement
    before_len = content.index(new_string)
    start_line = content[:before_len].count("\n")
    end_line = start_line + new_string.count("\n")

    # Expand by context
    preview_start = max(0, start_line - context_lines)
    preview_end = min(len(lines), end_line + context_lines + 1)

    numbered: list[str] = []
    for i in range(preview_start, preview_end):
        numbered.append(f"{i + 1:>6}\t{lines[i]}")

    return "\n".join(numbered)
