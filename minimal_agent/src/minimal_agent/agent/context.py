"""Context — composes a MessageStore with a system prompt and projection strategy.

The Agent interacts with the conversation exclusively through this class.
Storage is append-only; projection is where shaping lives.

Context is also the single assembly point for what the LLM sees each call:
`assemble()` returns `get_messages()` plus content gathered from live
(RUN/CALL-placed) context sources, injected per the merge rule below.
Injected content is never persisted — the store only ever holds real
conversation.
"""

import logging
from pathlib import Path

from ..context_sources import (
    ContextSource,
    Placement,
    source_placement,
    source_tag,
)
from ..llm.types import Message, Role, TextPart
from ..system_prompt.builder import build_context_blocks
from .message_store import MessageStore

logger = logging.getLogger(__name__)

# Framing appended after injected blocks so the model knows the harness —
# not the user — put them there, and that they beat any prompt snapshots.
_MERGED_FRAMING = (
    "<system-reminder>\n"
    "The tagged blocks above were gathered fresh by the harness at the "
    "start of\nthis turn — they are not part of the user's message, and "
    "they supersede any\nsnapshots in the system prompt.\n"
    "</system-reminder>"
)
_CARRIER_FRAMING = (
    "<system-reminder>\n"
    "The tagged blocks above were gathered fresh by the harness for this "
    "model\ncall — they are not part of the conversation, and they "
    "supersede any\nsnapshots in the system prompt.\n"
    "</system-reminder>"
)


class _SafeSource:
    """Wraps a live source so a raising gather() degrades to None.

    A live-source failure happens mid-run, possibly after tools already
    mutated the world — a transient error (e.g. git index.lock contention)
    must not kill the run. SESSION gathering keeps its fail-fast behavior;
    this wrapper is only used on the message channel.
    """

    def __init__(self, src: ContextSource) -> None:
        self._src = src
        self.name = src.name
        self.tag = source_tag(src)

    async def gather(self, workspace_root: Path) -> str | None:
        try:
            return await self._src.gather(workspace_root)
        except Exception:
            logger.debug(
                "live source %r failed to gather; skipping",
                self.name,
                exc_info=True,
            )
            return None


class Context:
    def __init__(
        self,
        *,
        system_prompt: str | None = None,
        store: MessageStore | None = None,
        live_sources: list[ContextSource] | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        self._store = store if store is not None else MessageStore()
        self._system_prompt = system_prompt
        self._workspace_root = workspace_root
        sources = list(live_sources) if live_sources else []
        self._run_sources = [s for s in sources if source_placement(s) is Placement.RUN]
        self._call_sources = [
            s for s in sources if source_placement(s) is Placement.CALL
        ]
        # Cached RUN blocks for the current run. The (blocks, gathered)
        # pair distinguishes "not gathered yet" from "gathered, nothing
        # to inject".
        self._run_blocks: str | None = None
        self._run_gathered = False

    def add(self, msg: Message) -> None:
        """Append a message to the conversation."""
        self._store.append(msg)

    @property
    def store(self) -> MessageStore:
        """Access to the underlying store (for inspection, debugging, persistence)."""
        return self._store

    def get_messages(self) -> list[Message]:
        """Project the stored messages into what the LLM should see this turn.

        Assembles the message list fresh each call:
        1. Prepend system prompt if set.
        2. Apply the projection strategy to stored messages.

        The default projection returns all stored messages unmodified.
        Sync and pure — no I/O, no gathering, no injected blocks — so
        UIs, tests, and debuggers can call it at any frequency.
        """
        msgs: list[Message] = []
        if self._system_prompt is not None:
            msgs.append(Message(role=Role.SYSTEM, content=self._system_prompt))
        msgs.extend(self._project())
        return msgs

    def begin_run(self) -> None:
        """Mark a run boundary.

        Clears the cached RUN content so the next assemble() re-gathers
        it. Sync, no I/O — all gathering stays in assemble(). A context
        whose begin_run() is never called still degrades sanely: the
        first assemble() finds no cached RUN content and gathers then.
        """
        self._run_blocks = None
        self._run_gathered = False

    async def assemble(self) -> list[Message]:
        """The full input for one LLM call.

        get_messages() plus injected live content, per the merge rule:
        RUN blocks merge into a copy of the run's (last) user message and
        stay byte-stable until the next begin_run(); CALL blocks join
        that merge on the run's first call, and otherwise ride one
        standalone trailing user carrier. The output never contains two
        consecutive user-role messages, and never mutates or persists
        stored Messages — merges are model_copy replacements in the
        outgoing list only.
        """
        msgs = self.get_messages()
        if (
            not (self._run_sources or self._call_sources)
            or self._workspace_root is None
        ):
            return msgs

        if self._run_sources and not self._run_gathered:
            self._run_blocks = await self._gather_blocks(self._run_sources)
            self._run_gathered = True

        call_blocks: str | None = None
        if self._call_sources:
            call_blocks = await self._gather_blocks(self._call_sources)

        user_idx = next(
            (i for i in range(len(msgs) - 1, -1, -1) if msgs[i].role is Role.USER),
            None,
        )
        if user_idx is None and self._run_blocks:
            logger.debug("no user message to anchor RUN blocks; skipping this run")

        merged: list[str] = []
        if user_idx is not None and self._run_blocks:
            merged.append(self._run_blocks)
        if call_blocks and user_idx == len(msgs) - 1:
            # First call of a run: the user message is the tail, so CALL
            # blocks are exactly as fresh as RUN blocks — merge them too
            # rather than emit a consecutive user carrier.
            merged.append(call_blocks)
            call_blocks = None

        if merged:
            injected = "\n".join([*merged, _MERGED_FRAMING])
            msgs[user_idx] = _merge_into_user(msgs[user_idx], injected)

        if call_blocks:
            msgs.append(
                Message(
                    role=Role.USER,
                    content=f"{call_blocks}\n{_CARRIER_FRAMING}",
                )
            )

        return msgs

    async def _gather_blocks(self, sources: list[ContextSource]) -> str | None:
        """Gather and format one channel's sources, tolerating failures."""
        return await build_context_blocks(
            [_SafeSource(s) for s in sources],
            self._workspace_root,
            preamble=None,
        )

    def _project(self) -> list[Message]:
        """The projection strategy. Returns the messages the LLM should see.

        Default: return everything. Override point for future strategies
        (sliding window, summarization, token-aware truncation).
        """
        return self._store.messages


def _merge_into_user(msg: Message, injected: str) -> Message:
    """Return a copy of a user message with injected blocks appended.

    Never mutates `msg` — get_messages() shallow-copies the list, so the
    Message objects are shared with the store; an in-place edit would
    write injected blocks into the persisted transcript.
    """
    if isinstance(msg.content, str):
        content: str | list = f"{msg.content}\n\n{injected}"
    elif isinstance(msg.content, list):
        content = [*msg.content, TextPart(text=injected)]
    else:
        content = injected
    return msg.model_copy(update={"content": content})
