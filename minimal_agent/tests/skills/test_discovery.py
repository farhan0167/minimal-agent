"""Tests for skill discovery, parsing, validation, and resolution."""

from pathlib import Path

import pytest

from minimal_agent.skills import (
    SkillMeta,
    SkillNotFoundError,
    SkillSource,
    discover_skills,
    parse_frontmatter,
    resolve_skill,
    validate_skill_name,
)


def _write_skill(
    root: Path, name: str, description: str, dir_name: str | None = None
) -> Path:
    """Helper: create a SKILL.md under root/<dir_name>/."""
    dir_name = dir_name or name
    skill_dir = root / dir_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nBody.\n"
    )
    return skill_file


class TestParseFrontmatter:
    def test_basic(self):
        content = "---\nname: foo\ndescription: Does foo.\n---\n\nBody."
        assert parse_frontmatter(content) == ("foo", "Does foo.")

    def test_missing_frontmatter(self):
        assert parse_frontmatter("# Just markdown\n") == (None, None)

    def test_empty_content(self):
        assert parse_frontmatter("") == (None, None)

    def test_quoted_values(self):
        content = '---\nname: "my-skill"\ndescription: \'A skill.\'\n---\n'
        assert parse_frontmatter(content) == ("my-skill", "A skill.")

    def test_extra_fields_ignored(self):
        content = (
            "---\n"
            "name: foo\n"
            "description: Foo.\n"
            "license: MIT\n"
            "metadata:\n"
            "  author: me\n"
            "---\n"
        )
        assert parse_frontmatter(content) == ("foo", "Foo.")

    def test_no_closing_delimiter(self):
        # Still extracts what it can before running out of lines.
        content = "---\nname: foo\ndescription: Foo.\n"
        assert parse_frontmatter(content) == ("foo", "Foo.")

    def test_only_name(self):
        content = "---\nname: foo\n---\n"
        assert parse_frontmatter(content) == ("foo", None)


class TestValidateSkillName:
    def test_valid(self):
        assert validate_skill_name("commit", "commit") is None
        assert validate_skill_name("pdf-processing", "pdf-processing") is None
        assert validate_skill_name("a", "a") is None

    def test_empty(self):
        assert validate_skill_name("", "x") is not None

    def test_too_long(self):
        name = "a" * 65
        err = validate_skill_name(name, name)
        assert err is not None
        assert "max 64" in err

    def test_uppercase_rejected(self):
        assert validate_skill_name("Foo", "Foo") is not None

    def test_leading_hyphen(self):
        assert validate_skill_name("-foo", "-foo") is not None

    def test_trailing_hyphen(self):
        assert validate_skill_name("foo-", "foo-") is not None

    def test_consecutive_hyphens(self):
        err = validate_skill_name("foo--bar", "foo--bar")
        assert err is not None
        assert "consecutive" in err

    def test_dir_name_mismatch(self):
        err = validate_skill_name("foo", "bar")
        assert err is not None
        assert "does not match" in err


class TestDiscoverSkills:
    def test_empty_workspace(self, tmp_path: Path):
        assert discover_skills(tmp_path) == []

    def test_single_skill(self, tmp_path: Path):
        skills_dir = tmp_path / ".minimal_agent" / "skills"
        _write_skill(skills_dir, "commit", "Create commits.")

        skills = discover_skills(tmp_path)
        assert len(skills) == 1
        assert skills[0].name == "commit"
        assert skills[0].description == "Create commits."
        assert skills[0].source == SkillSource.PROJECT
        assert skills[0].shadowed_by is None

    def test_invalid_skill_skipped(self, tmp_path: Path):
        skills_dir = tmp_path / ".minimal_agent" / "skills"
        # name doesn't match dir name → skipped
        _write_skill(skills_dir, "wrong-name", "Desc.", dir_name="real-dir")
        _write_skill(skills_dir, "good", "Desc.")

        skills = discover_skills(tmp_path)
        assert [s.name for s in skills] == ["good"]

    def test_missing_description_skipped(self, tmp_path: Path):
        skills_dir = tmp_path / ".minimal_agent" / "skills"
        skill_dir = skills_dir / "broken"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: broken\n---\nBody.")

        assert discover_skills(tmp_path) == []

    def test_skill_md_missing(self, tmp_path: Path):
        skills_dir = tmp_path / ".minimal_agent" / "skills"
        (skills_dir / "empty").mkdir(parents=True)
        assert discover_skills(tmp_path) == []

    def test_ancestor_walk(self, tmp_path: Path):
        # Skill defined at repo root, workspace is a subdirectory.
        skills_dir = tmp_path / ".minimal_agent" / "skills"
        _write_skill(skills_dir, "deploy", "Deploy the app.")

        subdir = tmp_path / "src" / "nested"
        subdir.mkdir(parents=True)

        skills = discover_skills(subdir)
        assert len(skills) == 1
        assert skills[0].name == "deploy"

    def test_shadowing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        # Put a "user home" inside tmp_path via HOME env override.
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))

        user_skills = home / ".minimal_agent" / "skills"
        project_skills = tmp_path / "proj" / ".minimal_agent" / "skills"

        _write_skill(user_skills, "commit", "User commit skill.")
        _write_skill(user_skills, "review-pr", "Review PRs.")
        _write_skill(project_skills, "commit", "Project commit skill.")

        workspace = tmp_path / "proj"
        skills = discover_skills(workspace)

        # Project "commit" wins, user "commit" is shadowed.
        active = [s for s in skills if s.shadowed_by is None]
        active_names = {s.name for s in active}
        assert active_names == {"commit", "review-pr"}

        project_commit = next(
            s for s in active if s.name == "commit"
        )
        assert project_commit.description == "Project commit skill."
        assert project_commit.source == SkillSource.PROJECT

        shadowed = [s for s in skills if s.shadowed_by is not None]
        assert len(shadowed) == 1
        assert shadowed[0].name == "commit"
        assert shadowed[0].source == SkillSource.USER
        assert shadowed[0].shadowed_by == SkillSource.PROJECT


class TestResolveSkill:
    def _make(self, name: str, shadowed: bool = False) -> SkillMeta:
        return SkillMeta(
            name=name,
            description="d",
            path=Path(f"/fake/{name}/SKILL.md"),
            source=SkillSource.PROJECT,
            shadowed_by=SkillSource.USER if shadowed else None,
        )

    def test_exact_match(self):
        skills = [self._make("commit"), self._make("review")]
        assert resolve_skill("commit", skills).name == "commit"

    def test_strips_slash(self):
        skills = [self._make("commit")]
        assert resolve_skill("/commit", skills).name == "commit"

    def test_strips_dollar(self):
        skills = [self._make("commit")]
        assert resolve_skill("$commit", skills).name == "commit"

    def test_case_insensitive(self):
        skills = [self._make("commit")]
        assert resolve_skill("COMMIT", skills).name == "commit"

    def test_shadowed_not_matched(self):
        skills = [self._make("commit", shadowed=True)]
        with pytest.raises(SkillNotFoundError):
            resolve_skill("commit", skills)

    def test_not_found_lists_available(self):
        skills = [self._make("commit"), self._make("review")]
        with pytest.raises(SkillNotFoundError) as exc:
            resolve_skill("deploy", skills)
        assert exc.value.available == ["commit", "review"]
