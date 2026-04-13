"""Skill discovery — scan the filesystem, parse SKILL.md frontmatter, index.

A skill is a directory containing a ``SKILL.md`` file with YAML frontmatter
(``name`` + ``description``) followed by markdown body content. Skills are
discovered from two roots, in priority order:

1. Project-local: ``.minimal_agent/skills/`` in the workspace root and each
   ancestor directory (ancestor walk).
2. User home: ``~/.minimal_agent/skills/``.

First-found wins (case-insensitive). Later duplicates are still returned in
the list with ``shadowed_by`` set so listings can show overrides.

Frontmatter parsing is intentionally line-based — no YAML parser dependency.
Only ``name`` and ``description`` are extracted; other fields are ignored.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .errors import SkillNotFoundError

SKILLS_DIR_NAME = ".minimal_agent/skills"
SKILL_FILE_NAME = "SKILL.md"

# Per https://agentskills.io/specification: 1-64 chars, lowercase alphanumeric
# and hyphens, no leading/trailing hyphen. Consecutive hyphens checked separately.
_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


class SkillSource(StrEnum):
    """Where a skill was discovered."""

    PROJECT = "project"
    USER = "user"


@dataclass(frozen=True)
class SkillMeta:
    """Lightweight skill metadata parsed from SKILL.md frontmatter."""

    name: str
    description: str
    path: Path
    source: SkillSource
    shadowed_by: SkillSource | None = None


# --- Frontmatter parsing -----------------------------------------------------


def _strip_quotes(value: str) -> str:
    """Strip matching surrounding single or double quotes."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_frontmatter(content: str) -> tuple[str | None, str | None]:
    """Extract ``name`` and ``description`` from SKILL.md frontmatter.

    Returns ``(name, description)``. Either field may be ``None`` if
    missing or malformed.
    """
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return (None, None)

    name: str | None = None
    description: str | None = None

    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = _strip_quotes(value.strip())
        if not value:
            continue
        if key == "name":
            name = value
        elif key == "description":
            description = value

    return (name, description)


# --- Name validation ---------------------------------------------------------


def validate_skill_name(name: str, dir_name: str) -> str | None:
    """Validate a skill name per the Agent Skills Specification.

    Returns ``None`` if valid, or an error message string if invalid.
    """
    if not name:
        return "name is empty"
    if len(name) > 64:
        return f"name is {len(name)} chars, max 64"
    if "--" in name:
        return "name contains consecutive hyphens"
    if not _NAME_RE.match(name):
        return (
            "name must contain only lowercase letters, numbers, and hyphens, "
            "and must not start or end with a hyphen"
        )
    if name != dir_name:
        return f"name {name!r} does not match parent directory {dir_name!r}"
    return None


# --- Discovery ---------------------------------------------------------------


def discover_skill_roots(workspace_root: Path) -> list[tuple[SkillSource, Path]]:
    """Find all directories that may contain skills.

    Returns ``(source, path)`` pairs in priority order (highest first):

    1. Project-local: ancestor walk from ``workspace_root``, checking
       ``.minimal_agent/skills/`` at each level (nearest ancestor first).
    2. User home: ``~/.minimal_agent/skills/``.

    Only existing directories are returned.
    """
    roots: list[tuple[SkillSource, Path]] = []
    seen: set[Path] = set()

    workspace_root = workspace_root.resolve()
    for parent in (workspace_root, *workspace_root.parents):
        candidate = parent / SKILLS_DIR_NAME
        if candidate.is_dir():
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                roots.append((SkillSource.PROJECT, resolved))

    user = (Path.home() / SKILLS_DIR_NAME).resolve()
    if user.is_dir() and user not in seen:
        seen.add(user)
        roots.append((SkillSource.USER, user))

    return roots


def _warn(msg: str) -> None:
    print(f"[skills] warning: {msg}", file=sys.stderr)


def _load_skill_from_dir(
    skill_dir: Path, source: SkillSource
) -> SkillMeta | None:
    """Load one skill from a directory. Returns None if invalid (logs warning)."""
    skill_file = skill_dir / SKILL_FILE_NAME
    if not skill_file.is_file():
        return None

    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError as e:
        _warn(f"{skill_file}: cannot read ({e})")
        return None

    name, description = parse_frontmatter(content)

    # Fall back to directory name if frontmatter name missing.
    if name is None:
        name = skill_dir.name

    error = validate_skill_name(name, skill_dir.name)
    if error is not None:
        _warn(f"{skill_file}: {error}")
        return None

    if not description:
        _warn(f"{skill_file}: missing required 'description' field")
        return None

    if len(description) > 1024:
        _warn(
            f"{skill_file}: description is {len(description)} chars, max 1024"
        )
        return None

    return SkillMeta(
        name=name,
        description=description,
        path=skill_file,
        source=source,
    )


def discover_skills(workspace_root: Path) -> list[SkillMeta]:
    """Discover all available skills from all roots.

    Scans roots in priority order. First skill found by name (case-insensitive)
    wins. Later duplicates are returned with ``shadowed_by`` set.
    """
    roots = discover_skill_roots(workspace_root)
    results: list[SkillMeta] = []
    active_by_key: dict[str, SkillSource] = {}

    for source, root in roots:
        try:
            entries = sorted(root.iterdir(), key=lambda p: p.name)
        except OSError as e:
            _warn(f"{root}: cannot read directory ({e})")
            continue

        for entry in entries:
            if not entry.is_dir():
                continue
            meta = _load_skill_from_dir(entry, source)
            if meta is None:
                continue

            key = meta.name.lower()
            winner = active_by_key.get(key)
            if winner is None:
                active_by_key[key] = source
                results.append(meta)
            else:
                # Already have a higher-priority skill with this name.
                results.append(
                    SkillMeta(
                        name=meta.name,
                        description=meta.description,
                        path=meta.path,
                        source=meta.source,
                        shadowed_by=winner,
                    )
                )

    return results


# --- Resolution --------------------------------------------------------------


def _normalize_name(name: str) -> str:
    """Normalize a user/model-supplied skill name for matching."""
    return name.strip().lstrip("/").lstrip("$").lower()


def resolve_skill(name: str, skills: list[SkillMeta]) -> SkillMeta:
    """Resolve a skill name to its metadata.

    Case-insensitive. Strips leading ``/`` and ``$`` characters. Only matches
    active (non-shadowed) skills.

    Raises ``SkillNotFoundError`` if no match.
    """
    key = _normalize_name(name)
    for meta in skills:
        if meta.shadowed_by is not None:
            continue
        if meta.name.lower() == key:
            return meta

    available = [m.name for m in skills if m.shadowed_by is None]
    raise SkillNotFoundError(name, available)
