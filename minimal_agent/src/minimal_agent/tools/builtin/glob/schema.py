"""Input schema for the `glob` tool."""

from typing import Optional

from pydantic import BaseModel, Field


class GlobInput(BaseModel):
    """Find files by name pattern.

    Supports glob patterns like '**/*.py' or 'src/**/*.ts'.
    Returns matching file paths sorted by modification time.
    """

    pattern: str = Field(
        ..., description="The glob pattern to match files against."
    )
    path: Optional[str] = Field(
        None,
        description="The directory to search in. "
        "Defaults to the current working directory.",
    )
