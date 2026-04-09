"""Tests for edit_file helpers."""

from minimal_agent.tools.builtin.edit_file.helpers import (
    apply_edit,
    build_preview,
    find_match_count,
)


def test_find_match_count_zero():
    assert find_match_count("hello world", "xyz") == 0


def test_find_match_count_one():
    assert find_match_count("hello world", "world") == 1


def test_find_match_count_multiple():
    assert find_match_count("aaa", "a") == 3
    assert find_match_count("abab", "ab") == 2


def test_apply_edit_replaces_first_occurrence():
    result = apply_edit("aXbXc", "X", "Y")
    assert result == "aYbXc"


def test_apply_edit_multiline():
    content = "line1\nline2\nline3\n"
    result = apply_edit(content, "line2", "replaced")
    assert result == "line1\nreplaced\nline3\n"


def test_build_preview_shows_replacement_with_context():
    content = "a\nb\nc\nd\ne\nNEW\ng\nh\ni\nj\n"
    preview = build_preview(content, "NEW")
    assert "NEW" in preview
    # Should have line numbers
    assert "6" in preview


def test_build_preview_at_start_of_file():
    content = "NEW\nb\nc\nd\n"
    preview = build_preview(content, "NEW")
    assert "1" in preview
    assert "NEW" in preview


def test_build_preview_at_end_of_file():
    content = "a\nb\nc\nNEW"
    preview = build_preview(content, "NEW")
    assert "NEW" in preview
    assert "4" in preview


def test_build_preview_multiline_replacement():
    content = "a\nb\nX\nY\nZ\nc\nd\n"
    preview = build_preview(content, "X\nY\nZ")
    assert "X" in preview
    assert "Y" in preview
    assert "Z" in preview
