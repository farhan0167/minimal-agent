"""WorkspaceSource — workspace metadata as an ordinary SESSION source.

The former system_prompt/env.py, absorbed wholesale: the <workspace> block
is built inside gather(), and the framework dogfoods its own placement
protocol instead of hardcoding the block into a prompt builder.
"""

import datetime
import platform
from typing import TYPE_CHECKING

from .base import Placement

if TYPE_CHECKING:
    from ..agent.view import SessionView


class WorkspaceSource:
    """The <workspace> block — static facts about where the agent acts.

    Attached unconditionally by the Agent (every identity gets one), so
    the model always knows where it is acting. SESSION-placed: gathered
    once at the context's first assemble(), a snapshot by design.
    """

    placement = Placement.SESSION
    tag = "workspace"
    name = "workspace"

    async def gather(self, session: "SessionView") -> str | None:
        workspace_root = session.workspace_root
        if workspace_root is None:
            return None
        is_git = (workspace_root / ".git").is_dir()
        return (
            f"Working directory: {workspace_root}\n"
            f"Platform: {platform.system().lower()}\n"
            f"Date: {datetime.date.today().isoformat()}\n"
            f"Is git repo: {'yes' if is_git else 'no'}"
        )
