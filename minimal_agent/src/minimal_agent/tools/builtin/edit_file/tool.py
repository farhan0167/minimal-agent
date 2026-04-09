"""The ``edit_file`` tool — surgical find-and-replace edits."""

from pathlib import Path

from ...base import BaseTool
from ...context import ToolContext
from ...results import ValidationErr, ValidationOk, ValidationResult
from .._filesystem import is_path_within
from .helpers import apply_edit, build_preview, find_match_count
from .schema import EditFileInput


class EditFile(BaseTool[EditFileInput, dict]):
    name = "edit_file"
    input_schema = EditFileInput
    is_read_only = False

    def __init__(
        self,
        workspace_root: Path,
        read_timestamps: dict[str, float],
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.read_timestamps = read_timestamps

    async def validate(
        self, args: EditFileInput, ctx: ToolContext
    ) -> ValidationResult:
        path = Path(args.file_path)

        if not path.is_absolute():
            return ValidationErr("file_path must be an absolute path.")

        if not is_path_within(path, self.workspace_root):
            return ValidationErr(
                f"Path is outside the workspace root ({self.workspace_root})."
            )

        if not path.exists():
            return ValidationErr(f"File not found: {args.file_path}")

        if not path.is_file():
            return ValidationErr(f"Path is not a file: {args.file_path}")

        # Read-before-edit guard
        resolved = str(path.resolve())
        read_ts = self.read_timestamps.get(resolved)

        if read_ts is None:
            return ValidationErr(
                "File has not been read yet. "
                "Use read_file first to see its current contents."
            )

        file_mtime = path.stat().st_mtime
        if file_mtime > read_ts:
            return ValidationErr(
                "File has been modified since it was last read. "
                "Use read_file again to see the current contents."
            )

        # old_string / new_string checks
        if args.old_string == args.new_string:
            return ValidationErr(
                "old_string and new_string are identical — nothing to change."
            )

        content = path.read_text(encoding="utf-8")

        count = find_match_count(content, args.old_string)
        if count == 0:
            return ValidationErr(
                "old_string was not found in the file. "
                "Make sure it matches exactly, including whitespace and indentation."
            )
        if count > 1:
            return ValidationErr(
                f"old_string appears {count} times in the file. "
                "Include more surrounding context to make the match unique."
            )

        return ValidationOk()

    async def invoke(self, args: EditFileInput, ctx: ToolContext) -> dict:
        path = Path(args.file_path)
        content = path.read_text(encoding="utf-8")

        new_content = apply_edit(content, args.old_string, args.new_string)
        path.write_text(new_content, encoding="utf-8")

        # Update timestamp so subsequent edits/writes don't fail staleness check.
        self.read_timestamps[str(path.resolve())] = path.stat().st_mtime

        preview = build_preview(new_content, args.new_string)

        return {
            "file_path": args.file_path,
            "preview": preview,
        }

    def needs_permission(self, args: EditFileInput) -> bool:
        return True

    def permission_description(self, args: EditFileInput) -> str:
        old_lines = args.old_string.count("\n") + 1
        new_lines = args.new_string.count("\n") + 1
        return f"Edit {args.file_path} (replace {old_lines} lines with {new_lines})"

    def render_result_for_assistant(self, out: dict) -> str:
        return f"Edited {out['file_path']}\n\n{out['preview']}"
