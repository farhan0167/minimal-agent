"""Append-only message storage.

The single source of truth for the conversation. Never mutated for
context-window reasons — that's the projection's job.

When constructed with a path, each append() also writes one JSONL line
to disk. When constructed without a path, behavior is pure in-memory.
"""

import logging
from pathlib import Path

from ..llm.types import Message, Role

logger = logging.getLogger(__name__)

# Marker text committed in place of (or alongside) an assistant reply that was
# cut off mid-stream — e.g. the client disconnected while tokens were still
# arriving. Recorded truthfully so the model sees on the next turn that its
# previous response was interrupted and can react (resume, restate, etc.).
INTERRUPTED_RESPONSE_MARKER = "[response interrupted before completion]"


class MessageStore:
    def __init__(self, *, path: Path | None = None) -> None:
        self._messages: list[Message] = []
        self._path = path
        # Healing actions from_file() took (synthetic appends), recorded so
        # session loading can report them (e.g. on a session.loaded event).
        self.healing_actions: list[str] = []

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

        The store stays bound to `path`, so crash-healing appends are
        persisted: a resumed session's file matches the history the model
        is about to be given. For a read that must not touch the file, use
        read_only() — same parse, same healing, no path to write through.
        """
        return cls._load(path, bind=True)

    @classmethod
    def read_only(cls, path: Path) -> "MessageStore":
        """Load a transcript for inspection — never writes to `path`.

        Same parsing and crash-healing as from_file(), but the returned
        store has no path, so the synthetic messages healing appends live
        in memory only. The caller sees the healed transcript a resume
        would see; the file on disk is untouched.
        """
        return cls._load(path, bind=False)

    @classmethod
    def _load(cls, path: Path, *, bind: bool) -> "MessageStore":
        store = cls(path=path if bind else None)

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
        store._heal_trailing_user_message()
        return store

    def _validate_tool_pairs(self) -> None:
        """Verify tool_call / tool_result pairing integrity.

        Checks two directions:
        1. Every tool result must reference a preceding tool call.
           Violation → corruption → raise ValueError.
        2. Every tool call must have a matching tool result.
           Orphaned tool calls at the *tail* of the conversation are
           interrupt/crash artifacts — we append synthetic error results
           to close them (truthful: the tool *was* interrupted).
           Orphaned tool calls mid-conversation indicate deeper corruption
           → raise ValueError.
        """
        seen_tool_call_ids: set[str] = set()
        seen_tool_result_ids: set[str] = set()

        for msg in self._messages:
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    seen_tool_call_ids.add(tc.id)
            if msg.role == Role.TOOL and msg.tool_call_id:
                if msg.tool_call_id not in seen_tool_call_ids:
                    raise ValueError(
                        f"Orphaned tool result: tool_call_id={msg.tool_call_id!r} "
                        f"has no matching tool_call in a preceding assistant message"
                    )
                seen_tool_result_ids.add(msg.tool_call_id)

        orphaned_call_ids = seen_tool_call_ids - seen_tool_result_ids
        if not orphaned_call_ids:
            return

        # Determine which orphaned calls are at the tail vs mid-conversation.
        # Walk backwards: collect tool_call_ids from the last assistant message
        # that has tool_calls. Any orphaned ids in that set are tail orphans;
        # the rest are mid-conversation corruption.
        tail_call_ids: set[str] = set()
        for msg in reversed(self._messages):
            if msg.tool_calls:
                tail_call_ids = {tc.id for tc in msg.tool_calls}
                break

        tail_orphans = orphaned_call_ids & tail_call_ids
        mid_orphans = orphaned_call_ids - tail_orphans

        if mid_orphans:
            raise ValueError(
                f"Orphaned tool call(s) mid-conversation: {mid_orphans!r} "
                f"have no matching tool results — this indicates corruption"
            )

        # Tail orphans: append synthetic interrupt results (truthful record).
        for orphan_id in tail_orphans:
            msg = Message(
                role=Role.TOOL,
                tool_call_id=orphan_id,
                content=(
                    "error: tool execution was interrupted "
                    "— you may retry this tool call"
                ),
            )
            self.append(msg)
            self.healing_actions.append(f"synthetic_tool_result:{orphan_id}")
            logger.info(
                "Appended synthetic interrupt result for tool_call_id=%s",
                orphan_id,
            )

    def _heal_trailing_user_message(self) -> None:
        """Close a conversation that ends on an unanswered user message.

        A trailing user message with no following assistant reply is an
        interrupt/crash artifact: the request was persisted, but the response
        was cut off before any assistant message was committed (e.g. the
        client disconnected mid-stream). Left as-is, the next user message
        produces two user turns in a row, which many chat templates reject
        ("roles must alternate").

        We append a synthetic assistant message marking the interruption —
        the same truthful-record approach `_validate_tool_pairs` uses for
        orphaned tool calls. The model sees on its next turn that the prior
        response never completed.
        """
        if not self._messages:
            return
        if self._messages[-1].role != Role.USER:
            return

        self.append(Message(role=Role.ASSISTANT, content=INTERRUPTED_RESPONSE_MARKER))
        self.healing_actions.append("interrupted_response_marker")
        logger.info(
            "Healed trailing unanswered user message with an interrupted-"
            "response marker (likely mid-stream interrupt artifact)."
        )

    @property
    def messages(self) -> list[Message]:
        """Read-only view of all stored messages.

        Returns a copy so callers cannot mutate storage.
        """
        return list(self._messages)

    def __len__(self) -> int:
        return len(self._messages)
