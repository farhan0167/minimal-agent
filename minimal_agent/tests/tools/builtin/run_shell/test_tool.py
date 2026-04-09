"""Integration tests for the RunShell tool (validate + invoke)."""

from pathlib import Path

from minimal_agent.tools.builtin.run_shell import RunShell, RunShellInput
from minimal_agent.tools.builtin.run_shell.shell import ShellResult
from minimal_agent.tools.context import ToolContext


class TestValidation:
    async def test_valid_command(self, tmp_path: Path):
        tool = RunShell(workspace_root=tmp_path)
        args = RunShellInput(command="echo hi")
        result = await tool.validate(args, ToolContext())
        assert result.ok is True

    async def test_rejects_empty_command(self, tmp_path: Path):
        tool = RunShell(workspace_root=tmp_path)
        args = RunShellInput(command="   ")
        result = await tool.validate(args, ToolContext())
        assert result.ok is False
        assert "empty" in result.message.lower()

    async def test_rejects_banned_command(self, tmp_path: Path):
        tool = RunShell(workspace_root=tmp_path)
        args = RunShellInput(command="wget http://example.com")
        result = await tool.validate(args, ToolContext())
        assert result.ok is False


class TestInvoke:
    async def test_executes_command(self, tmp_path: Path):
        tool = RunShell(workspace_root=tmp_path)
        try:
            args = RunShellInput(command="echo hello world")
            result = await tool.invoke(args, ToolContext())
            assert "hello world" in result.stdout
            assert result.exit_code == 0
        finally:
            if tool._shell:
                await tool._shell.close()

    async def test_timeout_parameter_respected(self, tmp_path: Path):
        tool = RunShell(workspace_root=tmp_path)
        try:
            args = RunShellInput(command="sleep 999", timeout=500)
            result = await tool.invoke(args, ToolContext())
            assert result.interrupted is True
        finally:
            if tool._shell:
                await tool._shell.close()


class TestNeedsPermission:
    def test_safe_command_no_permission(self, tmp_path: Path):
        tool = RunShell(workspace_root=tmp_path)
        assert tool.needs_permission(RunShellInput(command="pwd")) is False
        assert tool.needs_permission(RunShellInput(command="git status")) is False
        assert tool.needs_permission(RunShellInput(command="ls -la")) is False

    def test_unsafe_command_needs_permission(self, tmp_path: Path):
        tool = RunShell(workspace_root=tmp_path)
        assert tool.needs_permission(RunShellInput(command="rm -rf /")) is True
        assert tool.needs_permission(RunShellInput(command="make build")) is True


class TestRenderResult:
    def test_stdout_only(self, tmp_path: Path):
        tool = RunShell(workspace_root=tmp_path)
        out = ShellResult(stdout="output\n", stderr="", exit_code=0, cwd="/tmp")
        rendered = tool.render_result_for_assistant(out)
        assert rendered == "output"

    def test_stdout_and_stderr(self, tmp_path: Path):
        tool = RunShell(workspace_root=tmp_path)
        out = ShellResult(stdout="out\n", stderr="err\n", exit_code=1, cwd="/tmp")
        rendered = tool.render_result_for_assistant(out)
        assert "out" in rendered
        assert "err" in rendered

    def test_interrupted(self, tmp_path: Path):
        tool = RunShell(workspace_root=tmp_path)
        out = ShellResult(
            stdout="", stderr="", exit_code=143, cwd="/tmp", interrupted=True
        )
        rendered = tool.render_result_for_assistant(out)
        assert "aborted" in rendered

    def test_no_output(self, tmp_path: Path):
        tool = RunShell(workspace_root=tmp_path)
        out = ShellResult(stdout="", stderr="", exit_code=0, cwd="/tmp")
        rendered = tool.render_result_for_assistant(out)
        assert rendered == "(No output)"
