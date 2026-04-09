"""Read-specific helpers: text content reading with line numbers."""

from pathlib import Path


def read_text_content(
    file_path: Path,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    """Read a text file and return its content with line metadata.

    Lines are formatted with `cat -n` style numbering (1-indexed, 6-char
    padded, tab-separated). The model depends on this format to reference
    specific lines in follow-up requests.
    """
    text = file_path.read_text(encoding="utf-8")
    all_lines = text.splitlines()
    total_lines = len(all_lines)

    start = offset or 0
    end = (start + limit) if limit else total_lines
    selected = all_lines[start:end]

    numbered = []
    for i, line in enumerate(selected, start=start + 1):
        numbered.append(f"{i:>6}\t{line}")

    return {
        "content": "\n".join(numbered),
        "num_lines": len(selected),
        "total_lines": total_lines,
        "start_line": start + 1,
    }
