"""Input schema for the `write_file` tool."""

from pydantic import BaseModel, Field


class WriteFileInput(BaseModel):
    """Write content to a file. Creates the file (and parent directories)
    if it doesn't exist. Overwrites the file if it does."""

    file_path: str = Field(
        ..., description="Absolute path to the file to write."
    )
    content: str = Field(
        ..., description="The full content to write to the file."
    )
