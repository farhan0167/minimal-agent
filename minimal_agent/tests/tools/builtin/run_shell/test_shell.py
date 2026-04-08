"""Tests for PersistentShell — the execution engine."""

import asyncio
from pathlib import Path

from tools.builtin.run_shell.shell import PersistentShell


class TestBasicExecution:
    async def test_echo(self, tmp_path: Path):
        shell = PersistentShell(cwd=tmp_path)
        try:
            result = await shell.execute("echo hello", timeout_ms=5_000)
            assert result.stdout.strip() == "hello"
            assert result.exit_code == 0
        finally:
            await shell.close()

    async def test_nonzero_exit(self, tmp_path: Path):
        shell = PersistentShell(cwd=tmp_path)
        try:
            result = await shell.execute("ls /nonexistent_path_xyz", timeout_ms=5_000)
            assert result.exit_code != 0
            assert result.stderr  # Should have an error message
        finally:
            await shell.close()

    async def test_stderr_captured(self, tmp_path: Path):
        shell = PersistentShell(cwd=tmp_path)
        try:
            result = await shell.execute(
                "echo err >&2", timeout_ms=5_000
            )
            assert "err" in result.stderr
        finally:
            await shell.close()


class TestPersistence:
    async def test_cwd_persists(self, tmp_path: Path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        shell = PersistentShell(cwd=tmp_path)
        try:
            await shell.execute(f"cd {subdir}", timeout_ms=5_000)
            result = await shell.execute("pwd", timeout_ms=5_000)
            assert result.stdout.strip() == str(subdir)
            assert result.cwd == str(subdir)
        finally:
            await shell.close()

    async def test_env_var_persists(self, tmp_path: Path):
        shell = PersistentShell(cwd=tmp_path)
        try:
            await shell.execute(
                "export MY_TEST_VAR=hello123", timeout_ms=5_000
            )
            result = await shell.execute(
                "echo $MY_TEST_VAR", timeout_ms=5_000
            )
            assert result.stdout.strip() == "hello123"
        finally:
            await shell.close()


class TestTimeout:
    async def test_command_times_out(self, tmp_path: Path):
        shell = PersistentShell(cwd=tmp_path)
        try:
            result = await shell.execute("sleep 999", timeout_ms=500)
            assert result.exit_code == 143
            assert result.interrupted is True
            assert "timed out" in result.stderr
        finally:
            await shell.close()

    async def test_shell_survives_timeout(self, tmp_path: Path):
        shell = PersistentShell(cwd=tmp_path)
        try:
            await shell.execute("sleep 999", timeout_ms=500)
            # Shell should still work after timeout.
            result = await shell.execute("echo alive", timeout_ms=5_000)
            assert result.stdout.strip() == "alive"
        finally:
            await shell.close()


class TestSyntaxValidation:
    async def test_syntax_error_caught(self, tmp_path: Path):
        shell = PersistentShell(cwd=tmp_path)
        try:
            result = await shell.execute(
                "if then fi done", timeout_ms=5_000
            )
            assert result.exit_code != 0
            assert result.stderr  # Should have an error message
        finally:
            await shell.close()


class TestStdinFromDevNull:
    async def test_read_gets_eof(self, tmp_path: Path):
        shell = PersistentShell(cwd=tmp_path)
        try:
            result = await shell.execute(
                "read -t 1 VAR; echo \"exit:$?\"",
                timeout_ms=5_000,
            )
            # `read` should fail (exit code 1) because stdin is /dev/null.
            assert "exit:1" in result.stdout
        finally:
            await shell.close()


class TestSerialization:
    async def test_concurrent_calls_serialize(self, tmp_path: Path):
        shell = PersistentShell(cwd=tmp_path)
        try:
            # Launch two commands concurrently — they should not interleave.
            results = await asyncio.gather(
                shell.execute("echo first", timeout_ms=5_000),
                shell.execute("echo second", timeout_ms=5_000),
            )
            outputs = {r.stdout.strip() for r in results}
            assert outputs == {"first", "second"}
        finally:
            await shell.close()
