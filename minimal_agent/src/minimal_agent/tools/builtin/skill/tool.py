"""The `skill` tool — Phase 2 of the two-phase skill loading pattern.

Phase 1 (the lightweight skill list) is injected into the system prompt by
`SkillsContextSource`. This tool handles Phase 2: the model calls it with a
skill name, and receives the full SKILL.md contents as a tool result. The
model then follows those instructions.

Read-only by design — this is just a file read, so no permission prompt.
"""

from dataclasses import dataclass
from typing import Optional

from ....skills import SkillMeta, resolve_skill
from ...base import BaseTool
from ...context import ToolContext
from .schema import SkillInput


@dataclass
class SkillOutput:
    """What the model receives when it invokes a skill."""

    skill: str
    path: str
    args: Optional[str]
    description: str
    prompt: str


class SkillTool(BaseTool[SkillInput, SkillOutput]):
    name = "skill"
    input_schema = SkillInput
    is_read_only = True

    def __init__(self, skills: list[SkillMeta]) -> None:
        self._skills = skills

    async def invoke(self, args: SkillInput, ctx: ToolContext) -> SkillOutput:
        meta = resolve_skill(args.skill, self._skills)
        prompt = meta.path.read_text(encoding="utf-8")
        return SkillOutput(
            skill=args.skill,
            path=str(meta.path),
            args=args.args,
            description=meta.description,
            prompt=prompt,
        )

    def render_result_for_assistant(self, out: SkillOutput) -> str:
        header = [f"Skill: {out.skill}"]
        if out.args:
            header.append(f"Args: {out.args}")
        header.append(f"Path: {out.path}")
        header.append("")
        return "\n".join(header) + out.prompt
