"""Scope — a node in the session's recording tree.

The uniform handle every recorded context hangs off. The session root is a
scope; any tool can mint a *child scope* for an agent it is about to run
(`ctx.scope.child(...)`), which allocates `agents/a-<id>/` under the current
scope with the identical artifact kit — transcript, trace, audit — linked
bidirectionally to its parent. Recording a whole tree of agents is
structural, not optional.

Two implementations, and only two:

- `RecordedScope` — bound to a directory. Built by `SessionManager` for the
  session root; `child()` builds another for `agents/a-<id>/`, sharing the
  session root's `BlobStore` (content addressing makes cross-scope dedup
  free) and forwarding usage to the root totals.
- `NullScope` — for bare (unrecorded) contexts. Emitter with zero sinks,
  in-memory store, children are NullScopes. No `None` checks anywhere.

Child scopes are immutable *records of runs*, never resumable conversations.
Everything here is best-effort: an unwritable child directory degrades the
child to a NullScope with a warning — the sub-agent still runs, the trail
degrades. See
[.claude/specifications/scopes-and-session-management.md](../.claude/specifications/scopes-and-session-management.md).
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import uuid4

from ..context_sources import ContextSource
from ..events import (
    AgentEnd,
    AgentEndStatus,
    AgentSpawn,
    CallResponse,
    Envelope,
    EventEmitter,
    RunStart,
    Sink,
)
from ..llm.types import Usage
from .message_store import MessageStore
from .sinks import BlobStore, CallLogSink, TraceSink

if TYPE_CHECKING:
    from .context import Context

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return (
        datetime.now(tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class UsageTotals:
    """Mutable usage accumulator with change notification.

    The root scope's totals are the session's: every scope in the tree
    forwards its per-call usage here, and the Session subscribes to write
    the running total through to session.json.
    """

    def __init__(self) -> None:
        self.usage: Usage | None = None
        self._listeners: list[Callable[[Usage], None]] = []

    def subscribe(self, fn: Callable[[Usage], None]) -> None:
        """Register a listener called with the running total after each add."""
        self._listeners.append(fn)

    def add(self, usage: Usage) -> None:
        if self.usage is None:
            self.usage = usage.model_copy()
        else:
            self.usage = Usage(
                prompt_tokens=self.usage.prompt_tokens + usage.prompt_tokens,
                completion_tokens=self.usage.completion_tokens
                + usage.completion_tokens,
                total_tokens=self.usage.total_tokens + usage.total_tokens,
            )
        for fn in self._listeners:
            try:
                fn(self.usage)
            except Exception:
                logger.debug("usage listener %r failed; continuing", fn, exc_info=True)


class ScopeMetaSink:
    """Per-scope observer riding the scope's own emitter.

    Captures the agent fingerprint from run.start (for agent.json) and
    accumulates usage from call.response into the scope's totals — and
    forwards it to the session root's totals, so session.json truthfully
    includes every nested agent. Accounting is a sink, not a host callback.
    """

    def __init__(
        self, totals: UsageTotals, root_totals: UsageTotals | None = None
    ) -> None:
        self.model: str | None = None
        self.backend: str | None = None
        self._totals = totals
        self._root_totals = root_totals

    def handle(self, env: Envelope) -> None:
        if isinstance(env.event, RunStart):
            self.model = env.event.model
            self.backend = env.event.backend
        elif isinstance(env.event, CallResponse) and env.event.usage:
            usage = Usage(**env.event.usage)
            self._totals.add(usage)
            if self._root_totals is not None:
                self._root_totals.add(usage)


@runtime_checkable
class Scope(Protocol):
    """A node in the session's recording tree."""

    events: EventEmitter
    store: MessageStore

    def new_context(
        self,
        *,
        system_prompt: str | None = None,
        live_sources: list[ContextSource] | None = None,
        workspace_root: Path | None = None,
    ) -> "Context": ...

    def child(
        self,
        *,
        spawned_by: str,
        task: str,
        tool_call_id: str | None = None,
    ) -> AbstractContextManager["Scope"]: ...

    def children_of(self, tool_call_id: str | None) -> list[str]: ...


class NullScope:
    """The unrecorded scope — zero sinks, in-memory store, Null children.

    Behavior of everything built on it is byte-identical to a recorded
    scope; nothing is ever written.
    """

    def __init__(self) -> None:
        self.events = EventEmitter(sinks=[])
        self.store = MessageStore()

    def new_context(
        self,
        *,
        system_prompt: str | None = None,
        live_sources: list[ContextSource] | None = None,
        workspace_root: Path | None = None,
    ) -> "Context":
        from .context import Context

        return Context(
            system_prompt=system_prompt,
            scope=self,
            live_sources=live_sources,
            workspace_root=workspace_root,
        )

    @contextmanager
    def child(
        self,
        *,
        spawned_by: str,
        task: str,
        tool_call_id: str | None = None,
    ) -> "Iterator[Scope]":
        yield NullScope()

    def children_of(self, tool_call_id: str | None) -> list[str]:
        return []


class RecordedScope:
    """A scope bound to a directory — the artifact kit lives here.

    The root scope's directory is the session directory; a child's is
    `<parent>/agents/a-<id>/`. Sinks are per-scope instances appending to
    per-scope files: concurrency safety across sibling scopes is isolation,
    not locking.
    """

    def __init__(
        self,
        scope_dir: Path,
        *,
        blobs: BlobStore,
        session_id: str | None = None,
        root_totals: UsageTotals | None = None,
        store: MessageStore | None = None,
        extra_sinks: list[Sink] | None = None,
    ) -> None:
        self._dir = scope_dir
        self._blobs = blobs
        self._session_id = session_id
        self._extra_sinks = list(extra_sinks) if extra_sinks else []
        self.totals = UsageTotals()
        # Root scope (root_totals=None): its own totals ARE the session's.
        self._root_totals = root_totals if root_totals is not None else self.totals
        self._meta_sink = ScopeMetaSink(self.totals, root_totals)
        self.events = EventEmitter(
            sinks=[
                TraceSink(scope_dir),
                CallLogSink(scope_dir, blobs=blobs),
                self._meta_sink,
                *self._extra_sinks,
            ]
        )
        self.store = (
            store
            if store is not None
            else MessageStore(path=scope_dir / "messages.jsonl")
        )
        # agent_ids of children, keyed by the tool_call_id that spawned them —
        # read back by the dispatcher to stamp tool.end with its children.
        self._spawned: dict[str | None, list[str]] = {}

    @property
    def dir(self) -> Path:
        return self._dir

    def new_context(
        self,
        *,
        system_prompt: str | None = None,
        live_sources: list[ContextSource] | None = None,
        workspace_root: Path | None = None,
    ) -> "Context":
        from .context import Context

        return Context(
            system_prompt=system_prompt,
            scope=self,
            live_sources=live_sources,
            workspace_root=workspace_root,
        )

    def children_of(self, tool_call_id: str | None) -> list[str]:
        return list(self._spawned.get(tool_call_id, []))

    @contextmanager
    def child(
        self,
        *,
        spawned_by: str,
        task: str,
        tool_call_id: str | None = None,
    ) -> "Iterator[Scope]":
        """Open a recorded home for a nested agent.

        On entry: allocates `agents/a-<id>/`, writes agent.json, emits
        agent.spawn on THIS emitter. On exit — always, even when the body
        raises or is cancelled — emits agent.end with a truthful status and
        finalizes agent.json. If the directory cannot be created, degrades
        to a NullScope: the sub-agent still runs, unrecorded.
        """
        agent_id = "a-" + uuid4().hex[:8]
        child_dir = self._dir / "agents" / agent_id
        try:
            child_dir.mkdir(parents=True, exist_ok=False)
        except OSError:
            logger.warning(
                "cannot create child scope dir %s; sub-agent runs unrecorded",
                child_dir,
                exc_info=True,
            )
            yield NullScope()
            return

        child = RecordedScope(
            child_dir,
            blobs=self._blobs,
            session_id=self._session_id,
            root_totals=self._root_totals,
            extra_sinks=self._extra_sinks,
        )
        self._spawned.setdefault(tool_call_id, []).append(agent_id)

        meta: dict = {
            "agent_id": agent_id,
            "spawned_by": spawned_by,
            "task": task,
            "parent": {
                "session_id": self._session_id,
                "run_id": self.events.run_id,
                "call_id": self.events.call_id,
                "tool_call_id": tool_call_id,
            },
            "created_at": _utc_now_iso(),
        }
        _write_agent_json(child_dir, meta)
        self.events.emit(
            AgentSpawn(
                agent_id=agent_id,
                spawned_by=spawned_by,
                task=task,
                tool_call_id=tool_call_id,
            )
        )

        t0 = time.monotonic()
        status = AgentEndStatus.COMPLETED
        try:
            yield child
        except (GeneratorExit, asyncio.CancelledError):
            status = AgentEndStatus.ABANDONED
            raise
        except BaseException:
            status = AgentEndStatus.ERROR
            raise
        finally:
            usage = child.totals.usage
            self.events.emit(
                AgentEnd(
                    agent_id=agent_id,
                    status=status,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    usage=usage.model_dump() if usage else None,
                )
            )
            meta.update(
                {
                    "model": child._meta_sink.model,
                    "backend": child._meta_sink.backend,
                    "ended_at": _utc_now_iso(),
                    "status": str(status),
                    "usage": usage.model_dump() if usage else None,
                }
            )
            _write_agent_json(child_dir, meta)


def _write_agent_json(child_dir: Path, meta: dict) -> None:
    """Best-effort write — a failed agent.json degrades the record's
    linkage, never the run."""
    try:
        (child_dir / "agent.json").write_text(json.dumps(meta, indent=2) + "\n")
    except OSError:
        logger.warning("cannot write agent.json under %s", child_dir, exc_info=True)
