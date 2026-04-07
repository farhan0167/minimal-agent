"""Append-only message storage.

The single source of truth for the conversation. Never mutated for
context-window reasons — that's the projection's job.

When constructed with a path, each append() also writes one JSONL line
to disk. When constructed without a path, behavior is pure in-memory.
"""

import logging
from pathlib import Path

from llm.types import Message

logger = logging.getLogger(__name__)


class MessageStore:
    def __init__(self, *, path: Path | None = None) -> None:
        self._messages: list[Message] = []
        self._path = path

    def append(self, msg: Message) -> None:
        """Append a message to the in-memory log and, if a path is set, to disk."""
        self._messages.append(msg)
        if self._path is not None:
            with open(self._path, "a") as f:
                f.write(msg.model_dump_json() + "\n")

    @classmethod
    def from_file(cls, path: Path) -> "MessageStore":
        """Rebuild a MessageStore from a JSONL file on disk.

        Validates tool_use/tool_result pairing after loading.
        Handles corrupt last line (crash artifact) gracefully.
        """
        store = cls(path=path)

        if path.exists():
            lines = path.read_text().splitlines()
            for i, raw in enumerate(lines):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    store._messages.append(Message.model_validate_json(raw))
                except Exception as e:
                    if i == len(lines) - 1:
                        logger.warning(
                            "Skipping corrupt last line in %s "
                            "(likely crash artifact): %s",
                            path,
                            e,
                        )
                    else:
                        raise ValueError(
                            f"Corrupt message at line {i + 1} in {path}: {e}"
                        ) from e

        store._validate_tool_pairs()
        return store

    def _validate_tool_pairs(self) -> None:
        """Verify every tool-result references a preceding tool_call."""
        seen_tool_call_ids: set[str] = set()
        for msg in self._messages:
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    seen_tool_call_ids.add(tc.id)
            if msg.role == "tool" and msg.tool_call_id:
                if msg.tool_call_id not in seen_tool_call_ids:
                    raise ValueError(
                        f"Orphaned tool result: tool_call_id={msg.tool_call_id!r} "
                        f"has no matching tool_call in a preceding assistant message"
                    )

    @property
    def messages(self) -> list[Message]:
        """Read-only view of all stored messages.

        Returns a copy so callers cannot mutate storage.
        """
        return list(self._messages)

    def __len__(self) -> int:
        return len(self._messages)
