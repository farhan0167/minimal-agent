"""Session — the user-facing root of a recording tree.

`Session` owns identity metadata, usage rollup, and the root `Scope`'s
Context. It no longer knows how anything is wired to disk: persistence
policy — where sessions live, which sinks record them — belongs to
`SessionManager`, the only code that knows the directory layout.

Child scopes under `agents/` are immutable records of nested-agent runs,
never sessions: not resumable, not listed, no config validation. See
[.claude/specifications/scopes-and-session-management.md](../.claude/specifications/scopes-and-session-management.md).
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..context_sources import ContextSource
from ..events import SessionCreated, SessionLoaded, Sink
from ..llm.types import Usage
from .context import Context
from .message_store import MessageStore
from .scope import RecordedScope
from .sinks import BlobStore

_DEFAULT_BASE_DIR = Path(".minimal_agent/sessions")


class SessionConfigMismatchError(Exception):
    """Raised when resuming a session with a different model or backend."""


@dataclass
class SessionMeta:
    """Flat bag of metadata that maps 1:1 to session.json."""

    session_id: str
    model: str
    backend: str
    created_at: datetime
    updated_at: datetime
    usage: Usage | None = None
    workspace_root: str | None = None

    def to_dict(self) -> dict:
        d = {
            "session_id": self.session_id,
            "model": self.model,
            "backend": self.backend,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "usage": self.usage.model_dump() if self.usage else None,
        }
        if self.workspace_root is not None:
            d["workspace_root"] = self.workspace_root
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SessionMeta":
        return cls(
            session_id=data["session_id"],
            model=data["model"],
            backend=data["backend"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            usage=Usage(**data["usage"]) if data.get("usage") else None,
            workspace_root=data.get("workspace_root"),
        )


class Session:
    """One conversation: meta + the root scope's Context.

    Usage accounting is automatic — the session subscribes to the root
    scope's totals, which every scope in the tree forwards to, so
    session.json reflects the true cost including nested agents. Hosts
    never call an accounting method.
    """

    def __init__(
        self,
        *,
        meta: SessionMeta,
        context: Context,
        session_dir: Path,
        scope: RecordedScope,
    ) -> None:
        self._meta = meta
        self._context = context
        self._session_dir = session_dir
        self._scope = scope
        scope.totals.subscribe(self._on_usage)

    @property
    def session_dir(self) -> Path:
        return self._session_dir

    @property
    def session_id(self) -> str:
        return self._meta.session_id

    @property
    def context(self) -> Context:
        return self._context

    @property
    def scope(self) -> RecordedScope:
        """The root of this session's recording tree."""
        return self._scope

    @property
    def model(self) -> str:
        return self._meta.model

    @property
    def backend(self) -> str:
        return self._meta.backend

    @property
    def created_at(self) -> datetime:
        return self._meta.created_at

    @property
    def updated_at(self) -> datetime:
        return self._meta.updated_at

    @property
    def usage(self) -> Usage | None:
        return self._meta.usage

    @property
    def workspace_root(self) -> str | None:
        return self._meta.workspace_root

    def _on_usage(self, total: Usage) -> None:
        """Root-totals listener: mirror the running total into session.json."""
        self._meta.usage = total.model_copy()
        self._meta.updated_at = datetime.now(tz=timezone.utc)
        self._save_metadata()

    def _save_metadata(self) -> None:
        """Write session.json — small file, rewritten in full."""
        meta_path = self._session_dir / "session.json"
        meta_path.write_text(json.dumps(self._meta.to_dict(), indent=2) + "\n")


class SessionManager:
    """Persistence policy — where sessions live and how they are recorded.

    The only code that knows the directory layout. Agents hold one (a
    default is constructed when none is given) and delegate their session
    factories to it; hosts construct one explicitly only to change policy:

        manager = SessionManager(base_dir=Path("/var/lib/app/sessions"))
        agent = Agent(llm, tools, workspace_root=root, sessions=manager)
    """

    def __init__(
        self,
        *,
        base_dir: Path = _DEFAULT_BASE_DIR,
        extra_sinks: list[Sink] | None = None,
    ) -> None:
        self._base_dir = base_dir
        # Appended to every scope's emitter in every session this manager
        # creates — the seam for live UI feeds, OTel exporters, etc.
        self._extra_sinks = list(extra_sinks) if extra_sinks else []

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def create_session(
        self,
        *,
        model: str,
        backend: str,
        behavior_prompt: str | None = None,
        workspace_root: str | None = None,
        context_sources: list[ContextSource] | None = None,
    ) -> Session:
        """Start a new session. Creates the directory and files on disk.

        Takes identity (behavior prompt + context sources), never a
        rendered prompt: the Context partitions sources by placement and
        gathers SESSION ones at its first assemble(). Creation does no
        gathering, no I/O beyond mkdir + metadata. Sources are runtime
        wiring, not persisted state.
        """
        now = datetime.now(tz=timezone.utc)
        meta = SessionMeta(
            session_id=now.strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:4],
            model=model,
            backend=backend,
            created_at=now,
            updated_at=now,
            workspace_root=workspace_root,
        )

        session_dir = self._base_dir / meta.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        scope = self._root_scope(session_dir, meta.session_id)
        context = scope.new_context(
            behavior_prompt=behavior_prompt,
            context_sources=context_sources,
            workspace_root=Path(workspace_root) if workspace_root else None,
        )

        session = Session(
            meta=meta, context=context, session_dir=session_dir, scope=scope
        )
        session._save_metadata()
        scope.events.emit(SessionCreated())
        return session

    def load_session(
        self,
        session_id: str,
        *,
        model: str,
        backend: str,
        behavior_prompt: str | None = None,
        context_sources: list[ContextSource] | None = None,
    ) -> Session:
        """Resume an existing session from disk.

        Validates that the current model and backend match what the
        session was created with. Raises SessionConfigMismatchError
        if they differ.

        context_sources are re-attached to the Context with the persisted
        workspace_root — gathered content is regenerated, never restored
        (SESSION sources re-gather at the resumed context's first
        assemble()), so sessions predating workspace_root persistence
        degrade to no gathering.
        """
        session_dir = self._base_dir / session_id
        meta = self.read_meta(session_id)

        mismatches = []
        if meta.model and meta.model != model:
            mismatches.append(f"model: session={meta.model!r}, current={model!r}")
        if meta.backend and meta.backend != backend:
            mismatches.append(f"backend: session={meta.backend!r}, current={backend!r}")
        if mismatches:
            raise SessionConfigMismatchError(
                "Cannot resume session with different LLM config: "
                + "; ".join(mismatches)
            )

        store = MessageStore.from_file(session_dir / "messages.jsonl")
        scope = self._root_scope(session_dir, session_id, store=store)
        context = scope.new_context(
            behavior_prompt=behavior_prompt,
            context_sources=context_sources,
            workspace_root=(Path(meta.workspace_root) if meta.workspace_root else None),
        )
        scope.events.emit(
            SessionLoaded(
                message_count=len(store),
                healed=list(store.healing_actions),
            )
        )

        return Session(meta=meta, context=context, session_dir=session_dir, scope=scope)

    def read_meta(self, session_id: str) -> SessionMeta:
        """Read a session's metadata without loading its messages.

        The cheap peek for hosts that need e.g. the workspace root or
        model before deciding how to resume a session. Reads only
        session.json, never the JSONL. Raises FileNotFoundError if the
        session doesn't exist.
        """
        meta_path = self._base_dir / session_id / "session.json"
        with open(meta_path) as f:
            return SessionMeta.from_dict(json.load(f))

    def list_sessions(self) -> list[SessionMeta]:
        """List all sessions by reading their metadata files.

        Returns a list of SessionMeta, sorted by updated_at
        descending (most recent first).
        """
        sessions: list[SessionMeta] = []
        if not self._base_dir.exists():
            return sessions

        for session_dir in self._base_dir.iterdir():
            if not session_dir.is_dir():
                continue
            meta_path = session_dir / "session.json"
            if meta_path.exists():
                with open(meta_path) as f:
                    sessions.append(SessionMeta.from_dict(json.load(f)))

        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def _root_scope(
        self,
        session_dir: Path,
        session_id: str,
        *,
        store: MessageStore | None = None,
    ) -> RecordedScope:
        """Wire the artifact kit for a session root.

        Recording is default-on exactly where persistence is: every
        session-backed context records; only bare contexts don't.
        """
        return RecordedScope(
            session_dir,
            blobs=BlobStore(session_dir / "blobs"),
            session_id=session_id,
            store=store,
            extra_sinks=self._extra_sinks,
        )
