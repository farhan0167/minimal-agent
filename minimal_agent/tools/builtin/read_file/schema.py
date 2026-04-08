"""Input schema for the `read_file` tool."""

from typing import Optional

from pydantic import BaseModel, Field


class ReadFileInput(BaseModel):
    """Read the contents of a file, with optional line offset and limit."""

    file_path: str = Field(
        ..., description="Absolute path to the file to read."
    )
    offset: Optional[int] = Field(
        None,
        ge=0,
        description="Line number to start reading from (0-indexed). "
        "Omit to start from the beginning.",
    )
    limit: Optional[int] = Field(
        None,
        gt=0,
        description="Maximum number of lines to return. "
        "Omit to read to the end of the file.",
    )
