"""Tests for ReadFileInput — argument coercion the model tends to trip on."""

import pytest
from pydantic import ValidationError

from minimal_agent.tools.builtin.read_file import ReadFileInput


class TestBlankOptionalCoercion:
    """Models often emit "" for an optional int instead of omitting it.
    Blank must coerce to None rather than fail the whole tool call."""

    @pytest.mark.parametrize("blank", ["", "   ", "\t"])
    def test_blank_offset_and_limit_become_none(self, blank: str):
        args = ReadFileInput(file_path="/x", offset=blank, limit=blank)
        assert args.offset is None
        assert args.limit is None

    def test_omitted_stays_none(self):
        args = ReadFileInput(file_path="/x")
        assert args.offset is None and args.limit is None

    def test_real_ints_preserved(self):
        args = ReadFileInput(file_path="/x", offset=5, limit=10)
        assert args.offset == 5 and args.limit == 10

    def test_numeric_strings_still_coerced(self):
        # Pydantic's own numeric-string coercion must still apply.
        args = ReadFileInput(file_path="/x", offset="5", limit="10")
        assert args.offset == 5 and args.limit == 10

    def test_non_blank_garbage_still_rejected(self):
        # Blank → None, but actual garbage must still be a validation error.
        with pytest.raises(ValidationError):
            ReadFileInput(file_path="/x", offset="abc")
