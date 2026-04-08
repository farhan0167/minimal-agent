"""The `glob` tool — finds files by name pattern."""

import glob as globlib
from pathlib import Path

from tools.base import BaseTool
from tools.builtin._filesystem import is_path_within, sort_by_mtime
from tools.context import ToolContext
from tools.results import ValidationErr, ValidationOk, ValidationResult

from .schema import GlobInput

MAX_RESULTS = 100


class Glob(BaseTool[GlobInput, dict]):
    name = "glob"
    input_schema = GlobInput
    is_read_only = True

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()

    async def validate(
        self, args: GlobInput, ctx: ToolContext
    ) -> ValidationResult:
        if not args.pattern.strip():
            return ValidationErr("Pattern cannot be empty.")

        if args.path is not None:
            path = Path(args.path)
            if path.is_absolute() and not is_path_within(
                path, self.workspace_root
            ):
                return ValidationErr(
                    f"Path is outside the workspace root ({self.workspace_root})."
                )

        return ValidationOk()

    async def invoke(self, args: GlobInput, ctx: ToolContext) -> dict:
        search_root = (
            Path(args.path)
            if args.path and Path(args.path).is_absolute()
            else self.workspace_root / (args.path or "")
        )

        matches = globlib.glob(
            args.pattern, root_dir=str(search_root), recursive=True
        )

        # Resolve to absolute paths
        abs_paths = [str(search_root / m) for m in matches]

        all_files = sort_by_mtime(abs_paths)
        truncated = len(all_files) > MAX_RESULTS

        return {
            "filenames": all_files[:MAX_RESULTS],
            "num_files": len(all_files),
            "truncated": truncated,
        }

    def render_result_for_assistant(self, out: dict) -> str:
        if out["num_files"] == 0:
            return "No files found"
        result = "\n".join(out["filenames"])
        if out["truncated"]:
            result += (
                "\n(Results truncated. "
                "Consider a more specific path or pattern.)"
            )
        return result
