"""Helpers for the run_shell tool: command validation and safety checks."""

import shlex
from pathlib import Path

from minimal_agent.tools.results import ValidationErr, ValidationOk, ValidationResult

BANNED_COMMANDS: frozenset[str] = frozenset(
    {
        "curl",
        "wget",
        "nc",
        "telnet",
        "lynx",
        "w3m",
        "links",
        "chrome",
        "firefox",
        "safari",
    }
)

# Commands where the base name alone is enough to consider safe.
# Adding "git" here would make ALL git subcommands (including push --force) safe,
# so commands that need subcommand qualification go in SAFE_SUBCOMMANDS instead.
SAFE_NAMES: frozenset[str] = frozenset(
    {
        "ls",
        "pwd",
        "echo",
        "cat",
        "head",
        "tail",
        "wc",
        "sort",
        "uniq",
        "diff",
        "date",
        "which",
        "tree",
        "file",
        "basename",
        "dirname",
        "realpath",
    }
)

# Commands that are only safe with a specific subcommand or flag.
# Matched via startswith against the full segment text.
SAFE_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "git status",
        "git diff",
        "git log",
        "git branch",
        "python --version",
        "node --version",
        "npm --version",
    }
)


def _split_segments(command: str) -> list[str]:
    """Split a (possibly compound) shell command into individual segments.

    Splits on ``|``, ``&&``, ``||``, ``;`` and returns the stripped text of
    each segment.  Best-effort — not a full shell parser.
    """
    normalised = command
    for sep in ("&&", "||", "|", ";"):
        normalised = normalised.replace(sep, "\n")

    segments: list[str] = []
    for segment in normalised.splitlines():
        segment = segment.strip()
        if segment:
            segments.append(segment)
    return segments


def _extract_command_names(command: str) -> list[str]:
    """Extract base command names from a (possibly compound) shell command.

    Splits on ``|``, ``&&``, ``||``, ``;`` and returns the first token of
    each segment.  Best-effort — not a full shell parser.
    """
    names: list[str] = []
    for segment in _split_segments(command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            # Malformed quoting — take the first whitespace-delimited word.
            tokens = segment.split()
        if tokens:
            # Handle env-var prefixes like ``FOO=bar cmd``.
            for tok in tokens:
                if "=" in tok and not tok.startswith("-"):
                    continue
                names.append(Path(tok).name)  # strip path prefix
                break
    return names


def _is_segment_safe(segment: str) -> bool:
    """True if a single command segment is safe.

    Checks the base command name against ``SAFE_NAMES``, then falls back
    to prefix-matching the full segment against ``SAFE_SUBCOMMANDS``.
    """
    try:
        tokens = shlex.split(segment)
    except ValueError:
        tokens = segment.split()

    # Extract the base command name (skipping env-var prefixes).
    name: str | None = None
    for tok in tokens:
        if "=" in tok and not tok.startswith("-"):
            continue
        name = Path(tok).name
        break

    if name is not None and name in SAFE_NAMES:
        return True

    return any(segment.startswith(sub) for sub in SAFE_SUBCOMMANDS)


def is_command_safe(command: str) -> bool:
    """True if *every* segment of a (possibly compound) command is safe."""
    segments = _split_segments(command)
    if not segments:
        return False
    return all(_is_segment_safe(seg) for seg in segments)


def validate_command(command: str, workspace_root: Path) -> ValidationResult:
    """Check *command* against banned-command and cd-containment rules."""
    cmd_names = _extract_command_names(command)

    for name in cmd_names:
        if name in BANNED_COMMANDS:
            return ValidationErr(
                f"Command '{name}' is not allowed. "
                f"Use a dedicated tool for network access."
            )

    # cd containment — only when cd is the primary command.
    stripped = command.strip()
    if stripped == "cd" or stripped.startswith("cd "):
        target = stripped[3:].strip() or str(Path.home())
        # Strip quotes if present.
        if (target.startswith('"') and target.endswith('"')) or (
            target.startswith("'") and target.endswith("'")
        ):
            target = target[1:-1]

        resolved = (workspace_root / target).resolve()
        try:
            resolved.relative_to(workspace_root.resolve())
        except ValueError:
            return ValidationErr(
                f"Cannot cd outside the workspace root ({workspace_root})."
            )

    return ValidationOk()
