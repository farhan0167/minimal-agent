"""The `grep` tool — searches file contents using ripgrep."""

from pathlib import Path

from ...base import BaseTool
from ...context import ToolContext
from ...results import ValidationErr, ValidationOk, ValidationResult
from .._filesystem import (
    is_path_within,
    sort_by_mtime,
    truncate_text,
)
from .helpers import (
    MAX_RESULTS,
    build_ripgrep_args,
    run_ripgrep,
)
from .schema import GrepInput


class Grep(BaseTool[GrepInput, dict]):
    name = "grep"
    input_schema = GrepInput
    is_read_only = True

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()

    async def validate(
        self, args: GrepInput, ctx: ToolContext
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

        if args.context_lines is not None and args.output_mode != "content":
            return ValidationErr(
                "context_lines is only valid with output_mode='content'."
            )

        return ValidationOk()

    async def invoke(self, args: GrepInput, ctx: ToolContext) -> dict:
        if args.path:
            search_path = (
                args.path
                if Path(args.path).is_absolute()
                else str(self.workspace_root / args.path)
            )
        else:
            search_path = str(self.workspace_root)

        rg_args = build_ripgrep_args(args)
        stdout, exit_code = await run_ripgrep(rg_args, search_path)

        if exit_code == 1 or not stdout.strip():
            return {
                "output_mode": args.output_mode,
                "content": "",
                "num_files": 0,
                "filenames": [],
                "total_lines": 0,
            }

        if args.output_mode == "files_with_matches":
            files = stdout.strip().split("\n")
            sorted_files = sort_by_mtime(files, limit=MAX_RESULTS)
            return {
                "output_mode": "files_with_matches",
                "content": "",
                "num_files": len(files),
                "filenames": sorted_files,
                "total_lines": 0,
            }

        elif args.output_mode == "count":
            lines = stdout.strip().split("\n")
            return {
                "output_mode": "count",
                "content": "\n".join(lines[:MAX_RESULTS]),
                "num_files": len(lines),
                "filenames": [],
                "total_lines": 0,
            }

        else:  # content
            truncated, total_lines = truncate_text(stdout)
            return {
                "output_mode": "content",
                "content": truncated,
                "num_files": 0,
                "filenames": [],
                "total_lines": total_lines,
            }

    def render_result_for_assistant(self, out: dict) -> str:
        mode = out["output_mode"]

        if mode == "files_with_matches":
            num = out["num_files"]
            if num == 0:
                return "No files found"
            filenames = out["filenames"]
            result = f"Found {num} file{'s' if num != 1 else ''}\n"
            result += "\n".join(filenames)
            if num > MAX_RESULTS:
                result += (
                    "\n(Results truncated. "
                    "Consider a more specific path or pattern.)"
                )
            return result

        elif mode == "count":
            if out["num_files"] == 0:
                return "No matches found"
            return out["content"]

        else:  # content
            if not out["content"]:
                return "No matches found"
            return out["content"]
