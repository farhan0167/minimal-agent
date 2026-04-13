"""Skills — lazy-loaded prompt templates discovered from disk.

See `.claude/specifications/skills-system.md` for the full design.
"""

from .discovery import (
    SKILL_FILE_NAME,
    SKILLS_DIR_NAME,
    SkillMeta,
    SkillSource,
    discover_skill_roots,
    discover_skills,
    parse_frontmatter,
    resolve_skill,
    validate_skill_name,
)
from .errors import SkillNotFoundError, SkillValidationError

__all__ = [
    "SKILL_FILE_NAME",
    "SKILLS_DIR_NAME",
    "SkillMeta",
    "SkillNotFoundError",
    "SkillSource",
    "SkillValidationError",
    "discover_skill_roots",
    "discover_skills",
    "parse_frontmatter",
    "resolve_skill",
    "validate_skill_name",
]
