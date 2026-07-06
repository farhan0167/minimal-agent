"""Skills — the lightweight skill metadata list baked into the prompt."""

from pathlib import Path

from ..skills import SkillMeta


class SkillsContextSource:
    """Injects the lightweight skill metadata list into the system prompt.

    Phase 1 of the two-phase skill loading pattern. The model reads this
    list and decides which skill to invoke via the `skill` tool.
    """

    def __init__(self, skills: list[SkillMeta]) -> None:
        self._skills = skills

    @property
    def name(self) -> str:
        return "availableSkills"

    async def gather(self, workspace_root: Path) -> str | None:
        active = [s for s in self._skills if s.shadowed_by is None]
        if not active:
            return None

        lines = [
            "The following skills are available. "
            "Call the `skill` tool with the skill name to load the full instructions:",
            "",
        ]
        for s in active:
            lines.append(f"- {s.name}: {s.description}")
        return "\n".join(lines)
