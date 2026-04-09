"""PersistentShell — a long-lived shell process for serial command execution.

Spawns a single bash (or $SHELL) login shell at construction time and reuses
it for every command.  IPC uses temp files rather than stream parsing — the
same strategy Claude Code uses — because it's robust against interleaved
stdout/stderr and avoids sentinel-string brittleness.
"""

import asyncio
import os
import signal
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ShellResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    cwd: str = ""
    interrupted: bool = False
    stdout_lines: int = 0
    stderr_lines: int = 0


_POLL_INTERVAL_S = 0.01  # 10 ms


class PersistentShell:
    """A persistent login shell that serialises command execution."""

    def __init__(self, cwd: Path) -> None:
        self._cwd = cwd
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

        # Temp files for IPC — one set reused across commands.
        self._id = uuid.uuid4().hex[:8]
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="agent-shell-"))
        self._stdout_file = self._tmp_dir / f"{self._id}-stdout"
        self._stderr_file = self._tmp_dir / f"{self._id}-stderr"
        self._status_file = self._tmp_dir / f"{self._id}-status"
        self._cwd_file = self._tmp_dir / f"{self._id}-cwd"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _ensure_started(self) -> asyncio.subprocess.Process:
        if self._process is not None and self._process.returncode is None:
            return self._process

        shell = os.environ.get("SHELL", "/bin/bash")
        self._process = await asyncio.create_subprocess_exec(
            shell,
            "-l",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._cwd),
            start_new_session=True,
        )
        return self._process

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def close(self) -> None:
        if self._process and self._process.returncode is None:
            self._process.stdin.close()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        self._cleanup_tmp()

    def _cleanup_tmp(self) -> None:
        for f in (
            self._stdout_file,
            self._stderr_file,
            self._status_file,
            self._cwd_file,
        ):
            f.unlink(missing_ok=True)
        self._tmp_dir.rmdir()

    # ------------------------------------------------------------------
    # Syntax validation
    # ------------------------------------------------------------------

    async def _check_syntax(self, command: str) -> str | None:
        """Return an error message if the command has syntax errors, else None."""
        shell = os.environ.get("SHELL", "/bin/bash")
        try:
            proc = await asyncio.create_subprocess_exec(
                shell,
                "-n",
                "-c",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=1)
            if proc.returncode != 0:
                return stderr.decode(errors="replace").strip()
        except asyncio.TimeoutError:
            pass  # If syntax check itself times out, let execution proceed.
        return None

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(self, command: str, timeout_ms: int) -> ShellResult:
        """Execute *command* in the persistent shell.

        Serialised via an asyncio.Lock — concurrent callers block until
        the previous command finishes.
        """
        async with self._lock:
            # Syntax pre-check.
            syntax_err = await self._check_syntax(command)
            if syntax_err:
                return ShellResult(
                    stderr=syntax_err,
                    exit_code=2,
                    cwd=str(self._cwd),
                )

            proc = await self._ensure_started()

            # Truncate temp files before each command.
            for f in (
                self._stdout_file,
                self._stderr_file,
                self._status_file,
                self._cwd_file,
            ):
                f.write_text("")

            # Build the wrapped command.
            wrapped = (
                f"eval {_shell_quote(command)} < /dev/null "
                f"> {self._stdout_file} 2> {self._stderr_file}\n"
                f"__EXIT_CODE=$?\n"
                f"pwd > {self._cwd_file}\n"
                f"echo $__EXIT_CODE > {self._status_file}\n"
            )

            proc.stdin.write(wrapped.encode())
            await proc.stdin.drain()

            # Poll for the status file.
            completed = await self._wait_for_completion(timeout_ms)

            if not completed:
                await self._kill_children()
                # Read whatever output is available.
                return self._read_result(timed_out=True)

            return self._read_result(timed_out=False)

    async def _wait_for_completion(self, timeout_ms: int) -> bool:
        start = time.monotonic()
        while True:
            # Shell died mid-command.
            if self._process and self._process.returncode is not None:
                return True

            try:
                content = self._status_file.read_text().strip()
                if content:
                    return True
            except OSError:
                pass

            elapsed_ms = (time.monotonic() - start) * 1000
            if elapsed_ms > timeout_ms:
                return False

            await asyncio.sleep(_POLL_INTERVAL_S)

    def _read_result(self, *, timed_out: bool) -> ShellResult:
        stdout = _safe_read(self._stdout_file)
        stderr = _safe_read(self._stderr_file)
        cwd_str = _safe_read(self._cwd_file).strip() or str(self._cwd)
        status_str = _safe_read(self._status_file).strip()

        if timed_out:
            exit_code = 143  # 128 + SIGTERM
            stderr = (stderr + "\nCommand execution timed out").strip()
        else:
            try:
                exit_code = int(status_str)
            except ValueError:
                exit_code = 1

        self._cwd = Path(cwd_str)

        return ShellResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            cwd=cwd_str,
            interrupted=timed_out,
            stdout_lines=stdout.count("\n") + (1 if stdout else 0),
            stderr_lines=stderr.count("\n") + (1 if stderr else 0),
        )

    # ------------------------------------------------------------------
    # Process management
    # ------------------------------------------------------------------

    async def _kill_children(self) -> None:
        if not self._process or self._process.returncode is not None:
            return

        pid = self._process.pid
        pids = self._get_child_pids(pid)
        for p in pids:
            try:
                os.kill(p, signal.SIGTERM)
            except ProcessLookupError:
                pass

        # Escalate to SIGKILL after 5 seconds.
        await asyncio.sleep(5)
        for p in pids:
            try:
                os.kill(p, signal.SIGKILL)
            except ProcessLookupError:
                pass

    @staticmethod
    def _get_child_pids(parent_pid: int) -> list[int]:
        try:
            result = os.popen(f"pgrep -P {parent_pid}").read()  # noqa: S605
            return [int(p) for p in result.split() if p.strip()]
        except (ValueError, OSError):
            return []


def _shell_quote(command: str) -> str:
    """Wrap *command* for use with ``eval``.

    The entire command is passed as a single-quoted string to ``eval``,
    which avoids double-expansion of shell metacharacters.  Internal
    single quotes are escaped with the ``'\\''`` idiom.
    """
    escaped = command.replace("'", "'\\''")
    return f"'{escaped}'"


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""
