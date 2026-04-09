"""Input schema for the `grep` tool."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class GrepInput(BaseModel):
    """Search file contents using regular expressions.

    Returns matching file paths sorted by modification time. Use
    output_mode='content' to see matching lines with context.
    """

    pattern: str = Field(
        ...,
        description="The regular expression pattern to search for in file contents.",
    )
    path: Optional[str] = Field(
        None,
        description="File or directory to search in. "
        "Defaults to the current working directory.",
    )
    glob: Optional[str] = Field(
        None,
        description='Glob pattern to filter files (e.g. "*.py", "*.{ts,tsx}").',
    )
    type: Optional[str] = Field(
        None,
        description='File type to search (e.g. "py", "js", "rust"). '
        "More efficient than glob for standard file types.",
    )
    output_mode: Literal["files_with_matches", "content", "count"] = Field(
        "files_with_matches",
        description='Output mode: "files_with_matches" returns file paths, '
        '"content" returns matching lines with context, '
        '"count" returns match counts per file.',
    )
    case_sensitive: bool = Field(
        False,
        description="Case-sensitive search. Default is case-insensitive.",
    )
    context_lines: Optional[int] = Field(
        None,
        ge=0,
        le=10,
        description="Number of context lines before and after each match. "
        'Only applies when output_mode is "content".',
    )
    multiline: bool = Field(
        False,
        description="Enable multiline matching where . matches newlines "
        "and patterns can span lines.",
    )
