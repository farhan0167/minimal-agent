"""EnvSource — workspace metadata as an ordinary SESSION source.

The former system_prompt/env.py, absorbed wholesale: the <env> block is
built inside gather(), and the framework dogfoods its own placement
protocol instead of hardcoding the block into a prompt builder.
"""

import datetime
import platform
from pathlib import Path

from .base import Placement


class EnvSource:
    """The <env> block — static facts about the workspace.

    Attached unconditionally by the Agent (every identity gets one), so
    the model always knows where it is acting. SESSION-placed: gathered
    once at the context's first assemble(), a snapshot by design.
    """

    placement = Placement.SESSION
    tag = "env"
    name = "env"

    async def gather(self, workspace_root: Path) -> str | None:
        is_git = (workspace_root / ".git").is_dir()
        return (
            f"Working directory: {workspace_root}\n"
            f"Platform: {platform.system().lower()}\n"
            f"Date: {datetime.date.today().isoformat()}\n"
            f"Is git repo: {'yes' if is_git else 'no'}"
        )
