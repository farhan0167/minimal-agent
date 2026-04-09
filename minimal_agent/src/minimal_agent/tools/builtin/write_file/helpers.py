"""Write-specific helpers: text content writing with directory creation."""

from pathlib import Path


def write_text_content(file_path: Path, content: str) -> dict:
    """Write content to a file, creating parent directories if needed.

    Returns metadata about the write: whether the file was created or
    updated, the absolute path, and the line count.
    """
    existed = file_path.exists()

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

    num_lines = len(content.splitlines()) if content else 0

    return {
        "type": "update" if existed else "create",
        "file_path": str(file_path.resolve()),
        "num_lines": num_lines,
    }
