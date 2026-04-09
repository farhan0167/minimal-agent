"""The `write_file` tool — writes a file to the workspace."""

from pathlib import Path

from ...base import BaseTool
from ...context import ToolContext
from ...results import ValidationErr, ValidationOk, ValidationResult
from .._filesystem import is_path_within
from .helpers import write_text_content
from .schema import WriteFileInput


class WriteFile(BaseTool[WriteFileInput, dict]):
    name = "write_file"
    input_schema = WriteFileInput
    is_read_only = False

    def __init__(
        self,
        workspace_root: Path,
        read_timestamps: dict[str, float],
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.read_timestamps = read_timestamps

    async def validate(
        self, args: WriteFileInput, ctx: ToolContext
    ) -> ValidationResult:
        path = Path(args.file_path)

        if not path.is_absolute():
            return ValidationErr("file_path must be an absolute path.")

        if not is_path_within(path, self.workspace_root):
            return ValidationErr(
                f"Path is outside the workspace root ({self.workspace_root})."
            )

        # Read-before-write: only for existing files.
        if path.exists():
            resolved = str(path.resolve())
            read_ts = self.read_timestamps.get(resolved)

            if read_ts is None:
                return ValidationErr(
                    "File exists but has not been read. "
                    "Use read_file first to see its current contents."
                )

            file_mtime = path.stat().st_mtime
            if file_mtime > read_ts:
                return ValidationErr(
                    "File has been modified since it was last read. "
                    "Use read_file again to see the current contents."
                )

        return ValidationOk()

    async def invoke(self, args: WriteFileInput, ctx: ToolContext) -> dict:
        path = Path(args.file_path)
        result = write_text_content(path, args.content)
        # Update timestamp so subsequent writes don't fail staleness check.
        self.read_timestamps[str(path.resolve())] = path.stat().st_mtime
        return result

    def needs_permission(self, args: WriteFileInput) -> bool:
        return True

    def permission_description(self, args: WriteFileInput) -> str:
        path = Path(args.file_path)
        num_lines = args.content.count("\n") + 1
        verb = "Overwrite" if path.exists() else "Create"
        return f"{verb} {args.file_path} ({num_lines} lines)"

    def render_result_for_assistant(self, out: dict) -> str:
        verb = "Created" if out["type"] == "create" else "Updated"
        return f"{verb} {out['file_path']} ({out['num_lines']} lines)"
