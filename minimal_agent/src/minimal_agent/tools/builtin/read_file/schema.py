"""Input schema for the `read_file` tool."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ReadFileInput(BaseModel):
    """Read the contents of a file, with optional line offset and limit."""

    file_path: str = Field(..., description="Absolute path to the file to read.")
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

    @field_validator("offset", "limit", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        """Coerce a blank/empty optional to None.

        Models frequently emit "" (or whitespace) for an optional int they
        don't want to use, instead of omitting the field. Pydantic won't parse
        "" as an int, so without this the whole tool call fails with a
        validation error before invoke() ever runs. Treat blank as "omitted".
        """
        if isinstance(v, str) and v.strip() == "":
            return None
        return v
