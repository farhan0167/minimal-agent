"""Session — the user-facing unit of conversation.

Owns identity, metadata, and the Context. Provides factory methods to
create new sessions and load existing ones. Messages are persisted via
the MessageStore's JSONL backend; metadata is persisted as session.json.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from llm.types import Usage

from .context import Context
from .message_store import MessageStore

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

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "model": self.model,
            "backend": self.backend,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "usage": self.usage.model_dump() if self.usage else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionMeta":
        return cls(
            session_id=data["session_id"],
            model=data["model"],
            backend=data["backend"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            usage=Usage(**data["usage"]) if data.get("usage") else None,
        )


class Session:
    def __init__(
        self,
        *,
        meta: SessionMeta,
        context: Context,
        base_dir: Path,
    ) -> None:
        self._meta = meta
        self._context = context
        self._base_dir = base_dir

    @property
    def session_dir(self) -> Path:
        return self._base_dir / self._meta.session_id

    @property
    def session_id(self) -> str:
        return self._meta.session_id

    @property
    def context(self) -> Context:
        return self._context

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

    def update_usage(self, usage: Usage) -> None:
        """Accumulate usage from an API call and persist metadata."""
        if self._meta.usage is None:
            self._meta.usage = usage
        else:
            self._meta.usage = Usage(
                prompt_tokens=self._meta.usage.prompt_tokens
                + usage.prompt_tokens,
                completion_tokens=self._meta.usage.completion_tokens
                + usage.completion_tokens,
                total_tokens=self._meta.usage.total_tokens
                + usage.total_tokens,
            )
        self._meta.updated_at = datetime.now(tz=timezone.utc)
        self._save_metadata()

    def _save_metadata(self) -> None:
        """Write session.json — small file, rewritten in full."""
        meta_path = self.session_dir / "session.json"
        meta_path.write_text(json.dumps(self._meta.to_dict(), indent=2) + "\n")

    @classmethod
    def create(
        cls,
        *,
        model: str,
        backend: str,
        system_prompt: str | None = None,
        base_dir: Path = _DEFAULT_BASE_DIR,
    ) -> "Session":
        """Start a new session. Creates the directory and files on disk."""
        now = datetime.now(tz=timezone.utc)
        meta = SessionMeta(
            session_id=now.strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:4],
            model=model,
            backend=backend,
            created_at=now,
            updated_at=now,
        )

        session_dir = base_dir / meta.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        store = MessageStore(path=session_dir / "messages.jsonl")
        context = Context(system_prompt=system_prompt, store=store)

        session = cls(meta=meta, context=context, base_dir=base_dir)
        session._save_metadata()
        return session

    @classmethod
    def load(
        cls,
        session_id: str,
        *,
        model: str,
        backend: str,
        system_prompt: str | None = None,
        base_dir: Path = _DEFAULT_BASE_DIR,
    ) -> "Session":
        """Resume an existing session from disk.

        Validates that the current model and backend match what the
        session was created with. Raises SessionConfigMismatchError
        if they differ.
        """
        session_dir = base_dir / session_id
        meta_path = session_dir / "session.json"

        with open(meta_path) as f:
            data = json.load(f)

        meta = SessionMeta.from_dict(data)

        mismatches = []
        if meta.model and meta.model != model:
            mismatches.append(
                f"model: session={meta.model!r}, "
                f"current={model!r}"
            )
        if meta.backend and meta.backend != backend:
            mismatches.append(
                f"backend: session={meta.backend!r}, "
                f"current={backend!r}"
            )
        if mismatches:
            raise SessionConfigMismatchError(
                "Cannot resume session with different LLM config: "
                + "; ".join(mismatches)
            )

        messages_path = session_dir / "messages.jsonl"
        store = MessageStore.from_file(messages_path)
        context = Context(system_prompt=system_prompt, store=store)

        return cls(meta=meta, context=context, base_dir=base_dir)

    @classmethod
    def list_sessions(
        cls,
        *,
        base_dir: Path = _DEFAULT_BASE_DIR,
    ) -> list[SessionMeta]:
        """List all sessions by reading their metadata files.

        Returns a list of SessionMeta, sorted by updated_at
        descending (most recent first).
        """
        sessions: list[SessionMeta] = []
        if not base_dir.exists():
            return sessions

        for session_dir in base_dir.iterdir():
            if not session_dir.is_dir():
                continue
            meta_path = session_dir / "session.json"
            if meta_path.exists():
                with open(meta_path) as f:
                    sessions.append(SessionMeta.from_dict(json.load(f)))

        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions
