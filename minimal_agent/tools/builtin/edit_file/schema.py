"""Input schema for the ``edit_file`` tool."""

from pydantic import BaseModel, Field


class EditFileInput(BaseModel):
    """Perform a surgical find-and-replace edit on a file. The old_string must
    appear exactly once in the file. Provide enough surrounding context in
    old_string to make the match unique."""

    file_path: str = Field(
        ..., description="Absolute path to the file to edit."
    )
    old_string: str = Field(
        ...,
        description=(
            "The exact text to find and replace. Must match exactly once "
            "in the file (including whitespace and indentation). Include "
            "enough surrounding lines to make the match unique."
        ),
    )
    new_string: str = Field(
        ...,
        description="The text to replace old_string with.",
    )
