"""Input schema for the `run_shell` tool."""

from typing import Optional

from pydantic import BaseModel, Field


class RunShellInput(BaseModel):
    """Execute a shell command in the workspace.

    The working directory persists between calls. Environment variables
    and virtual environments set in one command are available in the next.
    Shell state (local variables, subshells) does not persist.
    """

    command: str = Field(
        ..., description="The shell command to execute."
    )
    timeout: Optional[int] = Field(
        None,
        gt=0,
        le=600_000,
        description="Optional timeout in milliseconds (max 600000). "
        "Defaults to 120000 (2 minutes).",
    )
