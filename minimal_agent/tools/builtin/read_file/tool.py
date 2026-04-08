"""The `read_file` tool — reads a file from the workspace."""

import time
from pathlib import Path

from tools.base import BaseTool
from tools.builtin._filesystem import MAX_FILE_SIZE_BYTES, is_path_within
from tools.context import ToolContext
from tools.results import ValidationErr, ValidationOk, ValidationResult

from .helpers import read_text_content
from .schema import ReadFileInput


class ReadFile(BaseTool[ReadFileInput, dict]):
    name = "read_file"
    input_schema = ReadFileInput
    is_read_only = True

    def __init__(
        self,
        workspace_root: Path,
        read_timestamps: dict[str, float],
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.read_timestamps = read_timestamps

    async def validate(
        self, args: ReadFileInput, ctx: ToolContext
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
            return ValidationErr(f"Not a file: {args.file_path}")

        if args.offset is None and args.limit is None:
            size = path.stat().st_size
            if size > MAX_FILE_SIZE_BYTES:
                return ValidationErr(
                    f"File is {size:,} bytes (limit: {MAX_FILE_SIZE_BYTES:,}). "
                    f"Use offset/limit to read a portion."
                )

        return ValidationOk()

    async def invoke(self, args: ReadFileInput, ctx: ToolContext) -> dict:
        path = Path(args.file_path)
        result = read_text_content(path, offset=args.offset, limit=args.limit)
        self.read_timestamps[str(path.resolve())] = time.time()
        return result

    def render_result_for_assistant(self, out: dict) -> str:
        header = (
            f"Lines {out['start_line']}-"
            f"{out['start_line'] + out['num_lines'] - 1} "
            f"of {out['total_lines']} total"
        )
        return f"{header}\n{out['content']}"
