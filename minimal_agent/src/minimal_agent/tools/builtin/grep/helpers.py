"""Helpers for the grep tool: ripgrep invocation and output formatting."""

import asyncio
import shutil

from .schema import GrepInput

RIPGREP_TIMEOUT_S = 10
MAX_BUFFER_BYTES = 1_000_000  # 1 MB
MAX_RESULTS = 100


async def run_ripgrep(
    args: list[str],
    target: str,
    timeout_s: float = RIPGREP_TIMEOUT_S,
) -> tuple[str, int]:
    """Run ripgrep with the given arguments.

    Returns (stdout, exit_code). Exit code 1 means no matches (normal).
    On timeout or error, returns ("", 1).
    """
    rg_path = shutil.which("rg")
    if rg_path is None:
        raise RuntimeError(
            "ripgrep (rg) not found in PATH. Install it: "
            "https://github.com/BurntSushi/ripgrep#installation"
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            rg_path,
            *args,
            target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_s
        )
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        if len(stdout_bytes) > MAX_BUFFER_BYTES:
            stdout = stdout[:MAX_BUFFER_BYTES].rsplit("\n", 1)[0]
        return stdout, proc.returncode or 0
    except asyncio.TimeoutError:
        proc.kill()
        return "", 1
    except Exception:
        return "", 1


def build_ripgrep_args(input: GrepInput) -> list[str]:
    """Build ripgrep argument list from tool input."""
    args: list[str] = []

    # Output mode
    if input.output_mode == "files_with_matches":
        args.append("-l")
    elif input.output_mode == "count":
        args.append("-c")

    # Case sensitivity
    if not input.case_sensitive:
        args.append("-i")

    # Multiline
    if input.multiline:
        args.extend(["-U", "--multiline-dotall"])

    # Context lines (only for content mode)
    if input.output_mode == "content" and input.context_lines is not None:
        args.extend(["-C", str(input.context_lines)])

    # Line numbers (for content mode)
    if input.output_mode == "content":
        args.append("-n")

    # File filtering
    if input.glob:
        args.extend(["--glob", input.glob])
    if input.type:
        args.extend(["--type", input.type])

    # The pattern
    args.append(input.pattern)

    return args



