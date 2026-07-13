"""SessionView — the session as seen from inside.

The *outside* view of a session is `Session`/`SessionManager` (create, load,
list). The *plumbing* is `Scope` (how a session records itself). This module
is the third view: what code running **within** a session sees — its
identity, its conversation so far, a place to remember things, a way to be
observed, a way to spawn children.

One view is minted alongside every `Context` (in `Scope.new_context()`) and
threaded to both extension surfaces: `ToolContext.session` for tools, and
the `gather(session)` argument for context sources. Everything
session-specific reaches extension code through it — never through a tool's
or source's constructor, which would be agent-level state shared across
every session that agent serves.

Each field is a *facet*: the narrowest interface that serves its consumer.
The transcript is structurally read-only, events are fire-and-forget, and
`state_dir` is a fenced-off directory the framework never touches. New
session-scoped capabilities land here as new fields, additively.
"""

import tempfile
from collections.abc import Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import TYPE_CHECKING, overload

from ..llm.types import Message, ToolCall

if TYPE_CHECKING:
    from .message_store import MessageStore
    from .scope import Scope


class Transcript(Sequence[Message]):
    """Read-only view of the conversation so far.

    A `Sequence[Message]` over the store, with no mutating method. Writing
    to the conversation is the agent loop's job, exclusively: a source
    appending during `assemble()` — while `assemble()` is iterating that
    very store — is transcript corruption, and a tool appending directly
    bypasses the loop's yield contract. The read-only wrapper makes both
    unrepresentable rather than merely documented-against.

    The view is live, not a copy: it reflects the store as of each read,
    so a tool sees the messages that preceded it in the current turn.
    """

    def __init__(self, store: "MessageStore") -> None:
        self._store = store

    def __len__(self) -> int:
        return len(self._store)

    @overload
    def __getitem__(self, i: int) -> Message: ...

    @overload
    def __getitem__(self, i: slice) -> list[Message]: ...

    def __getitem__(self, i):
        return self._store.messages[i]

    def tool_calls(self, name: str | None = None) -> list[ToolCall]:
        """Every tool call in the conversation, oldest first.

        Optionally filtered by tool name — the recurring query ("what have
        I, this tool, done so far in this session?") shipped as a helper so
        every tool author doesn't rewrite the same scan.
        """
        calls: list[ToolCall] = []
        for msg in self._store.messages:
            for tc in msg.tool_calls or ():
                if name is None or tc.name == name:
                    calls.append(tc)
        return calls

    def __repr__(self) -> str:
        return f"Transcript({len(self)} messages)"


class SessionView:
    """The session as seen from inside.

    Handed to every tool invocation (`ToolContext.session`) and every
    context source (`gather(session)`). Facets, not internals.

    The two directories are the pair worth keeping straight:

        workspace_root  where the agent *acts*     — the user's world,
                                                     shared across sessions
        state_dir       where the agent *remembers* — this session's world,
                                                     private to it
    """

    def __init__(
        self,
        *,
        scope: "Scope",
        session_id: str | None = None,
        workspace_root: Path | None = None,
        state_dir: Path | None = None,
    ) -> None:
        self._scope = scope
        self._session_id = session_id
        self._workspace_root = workspace_root
        # None ⇒ unrecorded: state_dir lazily mints a tempdir on first use.
        self._state_dir = state_dir
        self._transcript = Transcript(scope.store)

    @property
    def id(self) -> str | None:
        """This session's id, or None for a bare (unrecorded) context."""
        return self._session_id

    @property
    def workspace_root(self) -> Path | None:
        """Where the agent acts. None when the context has no workspace."""
        return self._workspace_root

    @property
    def transcript(self) -> Transcript:
        """The conversation so far, read-only."""
        return self._transcript

    @property
    def events(self):
        """The observability seam. `emit()` is fire-and-forget and never
        raises, so user code can emit custom events into `events.jsonl` and
        every extra sink alongside the framework's own trace."""
        return self._scope.events

    @property
    def state_dir(self) -> Path:
        """Per-session user land — where the agent remembers.

        Recorded sessions: `<session_dir>/state/`, created on first access
        and re-attached by `load_session()`, so a note written in run 1 is
        readable in run 40. Bare contexts: a lazily created tempdir —
        scratch, evaporates, byte-identical behavior otherwise.

        Always a real, writable directory: callers never branch on None.
        The framework never reads, writes, migrates, or garbage-collects
        anything under it. That fence is what keeps the rest of the session
        directory private and evolvable.
        """
        if self._state_dir is None:
            # Unrecorded: scratch space with the same shape, no durability.
            # Best-effort cleanup is the OS tempdir policy's business.
            self._state_dir = Path(tempfile.mkdtemp(prefix="minimal-agent-state-"))
        self._state_dir.mkdir(parents=True, exist_ok=True)
        return self._state_dir

    def spawn(
        self,
        *,
        spawned_by: str,
        task: str,
        tool_call_id: str | None = None,
    ) -> AbstractContextManager["Scope"]:
        """Open a recorded home for a nested agent.

        Yields the child `Scope`, whose `new_context()` builds the
        sub-agent's Context (carrying the child's own view: child transcript,
        child state_dir, same emitter tree). This is the one sanctioned route
        from extension code back into the recording tree — `spawn_agents` is
        the reference implementation.
        """
        return self._scope.child(
            spawned_by=spawned_by, task=task, tool_call_id=tool_call_id
        )

    def __repr__(self) -> str:
        return (
            f"SessionView(session_id={self._session_id!r}, "
            f"workspace_root={self._workspace_root!r}, "
            f"transcript={len(self._transcript)} messages)"
        )
