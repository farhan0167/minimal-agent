"""Context — composes a MessageStore with a behavior prompt and projection strategy.

The Agent interacts with the conversation exclusively through this class.
Storage is append-only; projection is where shaping lives.

Context is the single assembly point for what the LLM sees, across all
three gathering cadences: SESSION sources gather once at the first
`assemble()` (cached for the context's lifetime, rendered into the system
message together with the static behavior prompt), while live (RUN/CALL-
placed) sources are injected into the message list per the merge rule
below. Injected content is never persisted — the store only ever holds
real conversation.
"""

import logging
from pathlib import Path

from ..context_sources import (
    ContextSource,
    Placement,
    build_context_blocks,
    source_placement,
    source_tag,
)
from ..events import (
    CallRequest,
    EventEmitter,
    InjectedBlock,
    ProjectionEntry,
    SourceFailed,
    hash_messages,
)
from ..llm.types import Message, Role, TextPart
from .message_store import MessageStore
from .scope import NullScope, Scope
from .view import SessionView

logger = logging.getLogger(__name__)

# Prompt-baked context blocks are gathered once, at the context's first
# use — the preamble says so, so the model re-checks state instead of
# trusting a stale snapshot.
SNAPSHOT_PREAMBLE = (
    "As you answer the user's questions, "
    "you can use the following context.\n"
    "Note: these blocks are a snapshot taken at first use and do not\n"
    "update — use your tools to check current state when it matters:"
)

# Sentinel distinguishing "SESSION sources not gathered yet" from
# "gathered, nothing to contribute" (None is a valid gathered result).
_UNGATHERED = object()


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

    def __init__(self, src: ContextSource, events: EventEmitter) -> None:
        self._src = src
        self._events = events
        self.name = src.name
        self.tag = source_tag(src)

    async def gather(self, session: SessionView) -> str | None:
        try:
            return await self._src.gather(session)
        except Exception as e:
            # Type name only — exception messages can carry paths/secrets.
            self._events.emit(SourceFailed(source=self.name, error=type(e).__name__))
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
        behavior_prompt: str | None = None,
        scope: Scope | None = None,
        context_sources: list[ContextSource] | None = None,
        workspace_root: Path | None = None,
        session: SessionView | None = None,
    ) -> None:
        # The scope supplies both storage and the event seam. A bare
        # Context gets a NullScope: in-memory store, zero-sink emitter —
        # byte-identical behavior, nothing recorded.
        self._scope: Scope = scope if scope is not None else NullScope()
        self._store = self._scope.store
        self._behavior_prompt = behavior_prompt
        self._workspace_root = workspace_root
        # The inside view of this session, handed to every tool call and
        # every gather. Normally minted by Scope.new_context(), which knows
        # the session id and state dir; a bare Context() builds the degraded
        # one (no session id, tempdir state) from its NullScope.
        self._session = (
            session
            if session is not None
            else SessionView(scope=self._scope, workspace_root=workspace_root)
        )
        sources = list(context_sources) if context_sources else []
        self._session_sources = [
            s for s in sources if source_placement(s) is Placement.SESSION
        ]
        self._run_sources = [s for s in sources if source_placement(s) is Placement.RUN]
        self._call_sources = [
            s for s in sources if source_placement(s) is Placement.CALL
        ]
        # Cached SESSION blocks — the snapshot, taken at the first
        # ensure_session_gathered() and immutable thereafter.
        self._session_blocks: object = _UNGATHERED
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

    @property
    def scope(self) -> Scope:
        """The recording node this context hangs off (NullScope if bare)."""
        return self._scope

    @property
    def session(self) -> SessionView:
        """This session as seen from inside — the handle every tool call
        and every gather receives. One per Context, for its lifetime."""
        return self._session

    @property
    def system_prompt(self) -> str | None:
        """The stable system-prompt layer (behavior prompt + SESSION blocks),
        rendered from the cache. Its value changes exactly once — at the
        first ensure_session_gathered(); before that it is the behavior
        prompt alone. The Agent reads this to stamp it onto run.start as a
        run-level fact (after awaiting the ensure, so the event is
        truthful); the volatile layer (live injected blocks) is recorded
        separately as injected_run / injected_call."""
        blocks = None if self._session_blocks is _UNGATHERED else self._session_blocks
        parts = [p for p in (self._behavior_prompt, blocks) if p is not None]
        return "\n\n".join(parts) if parts else None

    @property
    def events(self) -> EventEmitter:
        """The scope's event seam — always present, zero sinks when bare."""
        return self._scope.events

    def get_messages(self) -> list[Message]:
        """Project the stored messages into what the LLM should see this turn.

        Assembles the message list fresh each call:
        1. Prepend system prompt if set.
        2. Apply the projection strategy to stored messages.

        The default projection returns all stored messages unmodified.
        Sync and pure — no I/O, no gathering, no injected blocks — so
        UIs, tests, and debuggers can call it at any frequency. The
        system message renders from the SESSION cache: before the first
        gather it carries the behavior prompt alone.
        """
        return self._with_system(self.project())

    def _with_system(self, projected: list[Message]) -> list[Message]:
        """Prepend the system message (if any) to a projection."""
        msgs: list[Message] = []
        system = self.system_prompt
        if system is not None:
            msgs.append(Message(role=Role.SYSTEM, content=system))
        msgs.extend(projected)
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

    async def ensure_session_gathered(self) -> None:
        """Idempotent first-gather of SESSION sources into the per-context
        cache — the snapshot moment. Called by Agent.run() before emitting
        RunStart (so the trace records the real rendered prompt) and by
        assemble() (so contexts driven without Agent.run() self-heal).
        Doubles as the host-facing preview trigger: await it, then read
        the sync `system_prompt` property.

        Fail-fast: a raising SESSION source propagates (unlike the live
        channels, where _SafeSource degrades a failure to None) — a
        broken source fails the first run loudly rather than silently
        shipping a degraded prompt. The cache is assigned only after the
        awaited gather completes, so a failed or cancelled first gather
        leaves it ungathered and the next call retries.
        """
        if self._session_blocks is not _UNGATHERED:
            return
        if not self._session_sources:
            self._session_blocks = None
            return
        self._session_blocks = await build_context_blocks(
            self._session_sources,
            self._session,
            preamble=SNAPSHOT_PREAMBLE,
        )

    async def assemble(self) -> list[Message]:
        """The full input for one LLM call.

        Ensures the SESSION snapshot exists (a no-op after the first
        call), then get_messages() plus injected live content, per the
        merge rule:
        RUN blocks merge into a copy of the run's (last) user message and
        stay byte-stable until the next begin_run(); CALL blocks join
        that merge on the run's first call, and otherwise ride one
        standalone trailing user carrier. The output never contains two
        consecutive user-role messages, and never mutates or persists
        stored Messages — merges are model_copy replacements in the
        outgoing list only.

        When an emitter is attached, every call emits one call.request
        event recording what was assembled; without one, behavior is
        byte-identical to an unrecorded context.
        """
        await self.ensure_session_gathered()
        # project() once: the same list is both sent and audited, so the
        # recorded ranges cannot drift from what the model actually saw.
        projected = self.project()
        msgs = self._with_system(projected)
        injected_run: InjectedBlock | None = None
        injected_call: InjectedBlock | None = None

        if self._run_sources or self._call_sources:
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
                # anchor is an index into the *projection*, which is what
                # audit rebuilds from the recorded ranges: user_idx is a
                # position in the assembled list, which the system message
                # (if rendered) shifts by one.
                offset = 1 if msgs[0].role is Role.SYSTEM else 0
                injected_run = InjectedBlock(anchor=user_idx - offset, text=injected)

            if call_blocks:
                carrier = f"{call_blocks}\n{_CARRIER_FRAMING}"
                msgs.append(Message(role=Role.USER, content=carrier))
                injected_call = InjectedBlock(anchor=None, text=carrier)

        self._emit_call_request(msgs, projected, injected_run, injected_call)
        return msgs

    def _emit_call_request(
        self,
        msgs: list[Message],
        projected: list[Message],
        injected_run: InjectedBlock | None,
        injected_call: InjectedBlock | None,
    ) -> None:
        """Record the audit payload for one assembled input.

        Every exit of assemble() passes through here — a call with no
        live injection is still a call the model saw.
        """
        self._scope.events.emit(
            CallRequest(
                projected=self._projection_recipe(projected),
                store_len=len(self._store),
                injected_run=injected_run,
                injected_call=injected_call,
                assembled_sha256=hash_messages(msgs),
            )
        )

    def _projection_recipe(self, projected: list[Message]) -> list[ProjectionEntry]:
        """Express this call's projection as an ordered list of audit entries.

        The recipe is what reconstruct_call() replays to rebuild the exact
        model input, so it must describe what project() actually returned —
        never what the default would have returned. Each entry is one of:

        - `(start, end)` — a contiguous run of stored messages, by reference,
          replayed as `messages.jsonl[start:end]`.
        - `Message` — one message the model saw that is not in the store, by
          value. `CallLogSink` interns it into `blobs/` at persist time, so
          the record on disk holds a `{"blob": "sha256:…"}` ref.

        Entries are in the order the model saw them, so the two forms compose:
        a rewriting projection records ranges around the messages it left
        alone and blobs for the ones it replaced.

        Stored messages are matched by object identity, which is exact for any
        projection that *selects* them (the default, windows, filters) and
        O(len(projected)). A projection that rewrites (`model_copy()`) or
        synthesizes a message misses that index by construction — the copy is
        a different object — and the message is captured by value instead.
        This is what makes a summarizing or eliding Context reconstructible:
        the framework already holds project()'s return value here, so it can
        quote what it cannot reference.

        Recording position, never provenance: a by-value entry asserts only
        "the model saw this message here". Which stored message a rewrite
        derives from is the projection author's semantics, not something the
        framework can know — and a value-similarity guess would be exactly the
        dishonesty this recipe exists to refuse.
        """
        stored = self._store.messages
        index = {id(m): i for i, m in enumerate(stored)}

        entries: list[ProjectionEntry] = []
        start = prev = None

        def close_range() -> None:
            nonlocal start, prev
            if start is not None:
                entries.append((start, prev + 1))
                start = prev = None

        for msg in projected:
            i = index.get(id(msg))
            if i is None:
                # Not in the store: a rewrite or a synthetic message. Quote it.
                close_range()
                entries.append(msg)
            elif start is None:
                start = prev = i
            elif i == prev + 1:
                prev = i
            else:
                # A gap or a step backwards — both just start a new range, so
                # reordering selections are expressible too.
                close_range()
                start = prev = i
        close_range()
        return entries

    async def _gather_blocks(self, sources: list[ContextSource]) -> str | None:
        """Gather and format one channel's sources, tolerating failures."""
        return await build_context_blocks(
            [_SafeSource(s, self._scope.events) for s in sources],
            self._session,
            preamble=None,
        )

    def project(self) -> list[Message]:
        """The projection strategy: the messages the LLM should see.

        Default: everything in the store. Override to implement a sliding
        window, summarization, token-aware truncation, etc. Supply the
        subclass to an Agent with `Agent(..., context_cls=MyContext)`.

        Contract:
        - Return a list of Messages for the LLM; the framework sends them
          in the order returned.
        - MUST NOT mutate the store. Projection is a *view*; the durable
          transcript is what the store holds. Filter and copy — never
          `self._store.messages.pop()`.
        - Called on every LLM call in the loop. Keep it cheap, or cache
          against the store's length.

        Whatever this returns is replayable by audit.reconstruct_call().
        Messages returned *as stored* (same objects) are recorded on
        call.request as store-index ranges; messages this method rewrites or
        synthesizes are captured by value into `blobs/`, since they exist
        nowhere else. Either way the recorded recipe reproduces exactly what
        the model saw — a summarizing or eliding subclass costs nothing but
        the bytes of the messages it invents. See _projection_recipe().
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
