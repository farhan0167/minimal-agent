"""Exceptions raised by the skills module."""

from pathlib import Path


class SkillNotFoundError(Exception):
    """Raised when a skill name doesn't match any discovered skill."""

    def __init__(self, name: str, available: list[str]) -> None:
        self.name = name
        self.available = available
        listing = ", ".join(available) if available else "(none)"
        super().__init__(
            f"Skill {name!r} not found. Available skills: {listing}"
        )


class SkillValidationError(Exception):
    """Raised when a SKILL.md fails validation during discovery."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")
