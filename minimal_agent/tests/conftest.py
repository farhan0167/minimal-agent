"""Shared test fixtures."""

from pathlib import Path

from minimal_agent.agent import NullScope, SessionView


def bare_view(workspace_root: Path | None = None) -> SessionView:
    """An unrecorded SessionView for testing a source or tool in isolation.

    Empty transcript, zero-sink emitter, tempdir-backed state_dir — the same
    degraded view a bare Context() builds. Sources under test only need the
    workspace root; anything exercising state or the transcript should build
    a real session instead.
    """
    return SessionView(scope=NullScope(), workspace_root=workspace_root)
