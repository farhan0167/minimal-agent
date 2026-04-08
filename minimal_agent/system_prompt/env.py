"""Environment block — workspace metadata for the system prompt."""

import datetime
import platform
from pathlib import Path


def build_env_block(workspace_root: Path) -> str:
    """Build the <env> XML block with workspace metadata.

    Always included in the system prompt. Contains static facts about
    the workspace that don't change mid-conversation.
    """
    is_git = (workspace_root / ".git").is_dir()

    return (
        f"<env>\n"
        f"Working directory: {workspace_root}\n"
        f"Platform: {platform.system().lower()}\n"
        f"Date: {datetime.date.today().isoformat()}\n"
        f"Is git repo: {'yes' if is_git else 'no'}\n"
        f"</env>"
    )
