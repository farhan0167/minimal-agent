"""Input schema for the `skill` tool."""

from typing import Optional

from pydantic import BaseModel, Field


class SkillInput(BaseModel):
    """Load a local skill definition and its instructions."""

    skill: str = Field(
        ...,
        description="The skill name to load (e.g. 'commit', 'review-pr').",
    )
    args: Optional[str] = Field(
        None,
        description=(
            "Optional free-form arguments to pass to the skill. "
            "The tool echoes these back; the skill prompt interprets them."
        ),
    )
