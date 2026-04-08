"""The `run_shell` tool — executes commands in a persistent shell."""

from pathlib import Path

from tools.base import BaseTool
from tools.context import ToolContext
from tools.results import ValidationErr, ValidationResult

from tools.builtin._filesystem import truncate_text

from .helpers import is_command_safe, validate_command
from .schema import RunShellInput
from .shell import PersistentShell, ShellResult

DEFAULT_TIMEOUT_MS = 120_000  # 2 minutes


class RunShell(BaseTool[RunShellInput, ShellResult]):
    name = "run_shell"
    input_schema = RunShellInput
    is_read_only = False

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self._shell: PersistentShell | None = None

    def _get_shell(self) -> PersistentShell:
        if self._shell is None or not self._shell.is_alive:
            self._shell = PersistentShell(cwd=self.workspace_root)
        return self._shell

    async def validate(
        self, args: RunShellInput, ctx: ToolContext
    ) -> ValidationResult:
        if not args.command.strip():
            return ValidationErr("Command cannot be empty.")

        return validate_command(args.command, self.workspace_root)

    async def invoke(
        self, args: RunShellInput, ctx: ToolContext
    ) -> ShellResult:
        shell = self._get_shell()
        timeout = args.timeout or DEFAULT_TIMEOUT_MS

        result = await shell.execute(args.command, timeout_ms=timeout)

        result.stdout, result.stdout_lines = truncate_text(result.stdout)
        result.stderr, result.stderr_lines = truncate_text(result.stderr)

        return result

    def needs_permission(self, args: RunShellInput) -> bool:
        return not is_command_safe(args.command)

    def render_result_for_assistant(self, out: ShellResult) -> str:
        parts: list[str] = []
        if out.stdout.strip():
            parts.append(out.stdout.strip())
        if out.stderr.strip():
            parts.append(out.stderr.strip())
        if out.interrupted:
            parts.append("<error>Command was aborted before completion</error>")
        if not parts:
            return "(No output)"
        return "\n".join(parts)
