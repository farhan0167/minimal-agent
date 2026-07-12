from pathlib import Path

import pytest

from minimal_agent.agent.context import Context, _merge_into_user
from minimal_agent.agent.message_store import MessageStore
from minimal_agent.agent.scope import NullScope
from minimal_agent.context_sources import Placement
from minimal_agent.events import (
    CallRequest,
    EventEmitter,
    SourceFailed,
    hash_messages,
)
from minimal_agent.llm.types import Message, Role, TextPart


def test_get_messages_with_system_prompt():
    ctx = Context(behavior_prompt="You are helpful.")
    ctx.add(Message(role=Role.USER, content="hi"))

    msgs = ctx.get_messages()

    assert len(msgs) == 2
    assert msgs[0].role == Role.SYSTEM
    assert msgs[0].content == "You are helpful."
    assert msgs[1].role == Role.USER


def test_get_messages_without_system_prompt():
    ctx = Context()
    ctx.add(Message(role=Role.USER, content="hi"))

    msgs = ctx.get_messages()

    assert len(msgs) == 1
    assert msgs[0].role == Role.USER


def test_get_messages_reflects_additions():
    ctx = Context(behavior_prompt="sys")
    ctx.add(Message(role=Role.USER, content="q"))

    assert len(ctx.get_messages()) == 2

    ctx.add(Message(role=Role.ASSISTANT, content="a"))

    assert len(ctx.get_messages()) == 3


def test_get_messages_is_pure():
    """Calling get_messages twice returns equivalent but distinct lists."""
    ctx = Context(behavior_prompt="sys")
    ctx.add(Message(role=Role.USER, content="hi"))

    a = ctx.get_messages()
    b = ctx.get_messages()

    assert a == b
    assert a is not b


def test_store_access():
    ctx = Context()
    ctx.add(Message(role=Role.USER, content="hi"))

    assert len(ctx.store) == 1
    assert ctx.store.messages[0].content == "hi"


# ---- live assembly (begin_run / assemble) ----------------------------------


class _LiveSource:
    """Counting live source; content includes the call count so tests can
    tell a cached serve from a re-gather."""

    def __init__(
        self,
        name: str = "live",
        placement: Placement = Placement.RUN,
        raises: bool = False,
        content: str | None = "fresh data",
    ):
        self.name = name
        self.placement = placement
        self.calls = 0
        self._raises = raises
        self._content = content

    async def gather(self, workspace_root) -> str | None:
        self.calls += 1
        if self._raises:
            raise RuntimeError("gather blew up")
        if self._content is None:
            return None
        return f"{self._content} (gather {self.calls})"


def _live_context(*sources, workspace_root="ws", store=None) -> Context:
    scope = NullScope()
    if store is not None:
        scope.store = store
    return Context(
        behavior_prompt="sys",
        scope=scope,
        context_sources=list(sources),
        workspace_root=Path(workspace_root) if workspace_root else None,
    )


def _no_consecutive_users(msgs: list[Message]) -> bool:
    return all(
        not (a.role is Role.USER and b.role is Role.USER)
        for a, b in zip(msgs, msgs[1:], strict=False)
    )


async def test_assemble_without_live_sources_equals_get_messages():
    ctx = Context(behavior_prompt="sys")
    ctx.add(Message(role=Role.USER, content="hi"))

    assert await ctx.assemble() == ctx.get_messages()


async def test_run_source_merges_into_user_copy():
    src = _LiveSource(name="gitStatus", placement=Placement.RUN)
    ctx = _live_context(src)
    ctx.add(Message(role=Role.USER, content="fix the test"))

    msgs = await ctx.assemble()

    merged = msgs[-1]
    assert merged.role is Role.USER
    # A model_copy replacement, not the stored object.
    assert merged is not ctx.store.messages[-1]
    assert merged.content.startswith("fix the test")
    assert '<context name="gitStatus">' in merged.content
    assert "fresh data (gather 1)" in merged.content
    assert "<system-reminder>" in merged.content
    # The stored message is untouched.
    assert ctx.store.messages[-1].content == "fix the test"


async def test_run_source_gathered_once_per_run_and_byte_stable():
    src = _LiveSource(placement=Placement.RUN)
    ctx = _live_context(src)
    ctx.add(Message(role=Role.USER, content="go"))
    ctx.begin_run()

    first = await ctx.assemble()
    ctx.add(Message(role=Role.ASSISTANT, content="working"))
    ctx.add(Message(role=Role.TOOL, content="ok", tool_call_id="tc_1"))
    second = await ctx.assemble()

    assert src.calls == 1
    user_first = next(m for m in first if m.role is Role.USER)
    user_second = next(m for m in second if m.role is Role.USER)
    assert user_first.content == user_second.content


async def test_begin_run_triggers_regather():
    src = _LiveSource(placement=Placement.RUN)
    ctx = _live_context(src)
    ctx.add(Message(role=Role.USER, content="run one"))

    ctx.begin_run()
    await ctx.assemble()
    assert src.calls == 1

    ctx.add(Message(role=Role.ASSISTANT, content="done"))
    ctx.add(Message(role=Role.USER, content="run two"))
    ctx.begin_run()
    msgs = await ctx.assemble()

    assert src.calls == 2
    assert "gather 2" in msgs[-1].content
    # The new run's blocks anchor to the new user message.
    assert msgs[-1].content.startswith("run two")


async def test_call_source_gathered_every_assemble():
    src = _LiveSource(name="watcher", placement=Placement.CALL)
    ctx = _live_context(src)
    ctx.add(Message(role=Role.USER, content="go"))
    ctx.begin_run()

    first = await ctx.assemble()
    # First call: trailing user message → CALL blocks merge into it.
    assert first[-1].role is Role.USER
    assert "gather 1" in first[-1].content
    assert _no_consecutive_users(first)

    ctx.add(Message(role=Role.ASSISTANT, content="working"))
    ctx.add(Message(role=Role.TOOL, content="ok", tool_call_id="tc_1"))
    second = await ctx.assemble()

    # Later call: trailing tool result → one standalone user carrier.
    assert src.calls == 2
    assert second[-1].role is Role.USER
    assert "gather 2" in second[-1].content
    assert second[-2].role is Role.TOOL
    assert _no_consecutive_users(second)
    # The carrier is assembly output only — never stored.
    assert ctx.store.messages[-1].role is Role.TOOL


async def test_two_call_sources_share_one_carrier():
    a = _LiveSource(name="a", placement=Placement.CALL)
    b = _LiveSource(name="b", placement=Placement.CALL)
    ctx = _live_context(a, b)
    ctx.add(Message(role=Role.USER, content="go"))
    ctx.add(Message(role=Role.ASSISTANT, content="working"))
    ctx.add(Message(role=Role.TOOL, content="ok", tool_call_id="tc_1"))

    msgs = await ctx.assemble()

    carriers = msgs[len(ctx.get_messages()) :]
    assert len(carriers) == 1
    assert '<context name="a">' in carriers[0].content
    assert '<context name="b">' in carriers[0].content


async def test_run_and_call_first_call_single_merged_message():
    run_src = _LiveSource(name="runner", placement=Placement.RUN)
    call_src = _LiveSource(name="caller", placement=Placement.CALL)
    ctx = _live_context(run_src, call_src)
    ctx.add(Message(role=Role.USER, content="go"))
    ctx.begin_run()

    msgs = await ctx.assemble()

    # Same length as the clean projection — no standalone carrier.
    assert len(msgs) == len(ctx.get_messages())
    merged = msgs[-1]
    assert '<context name="runner">' in merged.content
    assert '<context name="caller">' in merged.content
    assert _no_consecutive_users(msgs)


async def test_multimodal_user_message_gets_text_part():
    src = _LiveSource(placement=Placement.RUN)
    ctx = _live_context(src)
    ctx.add(
        Message(
            role=Role.USER,
            content=[TextPart(text="look at this")],
        )
    )

    msgs = await ctx.assemble()

    parts = msgs[-1].content
    assert isinstance(parts, list)
    assert len(parts) == 2
    assert '<context name="live">' in parts[-1].text
    # Stored message keeps its single part.
    assert len(ctx.store.messages[-1].content) == 1


async def test_no_user_message_skips_run_but_emits_call_carrier():
    run_src = _LiveSource(name="runner", placement=Placement.RUN)
    call_src = _LiveSource(name="caller", placement=Placement.CALL)
    ctx = _live_context(run_src, call_src)
    ctx.add(Message(role=Role.ASSISTANT, content="hello"))

    msgs = await ctx.assemble()

    assert msgs[-1].role is Role.USER
    assert '<context name="caller">' in msgs[-1].content
    assert "runner" not in msgs[-1].content
    assert all("runner" not in str(m.content) for m in msgs if m.content is not None)


async def test_all_sources_none_returns_clean_projection():
    src = _LiveSource(placement=Placement.RUN, content=None)
    ctx = _live_context(src)
    ctx.add(Message(role=Role.USER, content="hi"))

    assert await ctx.assemble() == ctx.get_messages()


async def test_no_workspace_root_skips_gathering():
    src = _LiveSource(placement=Placement.RUN)
    ctx = _live_context(src, workspace_root=None)
    ctx.add(Message(role=Role.USER, content="hi"))

    msgs = await ctx.assemble()

    assert src.calls == 0
    assert msgs == ctx.get_messages()


async def test_raising_source_skipped_others_injected():
    bad = _LiveSource(name="bad", placement=Placement.RUN, raises=True)
    good = _LiveSource(name="good", placement=Placement.RUN)
    ctx = _live_context(bad, good)
    ctx.add(Message(role=Role.USER, content="hi"))

    msgs = await ctx.assemble()

    assert '<context name="good">' in msgs[-1].content
    assert "bad" not in msgs[-1].content


async def test_injected_content_never_persisted(tmp_path):
    store = MessageStore(path=tmp_path / "messages.jsonl")
    src = _LiveSource(placement=Placement.RUN)
    ctx = _live_context(src, store=store)
    ctx.add(Message(role=Role.USER, content="hi"))

    await ctx.assemble()

    assert ctx.store.messages[-1].content == "hi"
    on_disk = (tmp_path / "messages.jsonl").read_text()
    assert "context name=" not in on_disk
    assert "system-reminder" not in on_disk


async def test_get_messages_never_gathers_or_injects():
    src = _LiveSource(placement=Placement.RUN)
    ctx = _live_context(src)
    ctx.add(Message(role=Role.USER, content="hi"))

    await ctx.assemble()
    clean = ctx.get_messages()

    assert src.calls == 1
    assert clean[-1].content == "hi"


# ---- observability (call.request emission + audit round-trip) ---------------


class _Recorder:
    def __init__(self):
        self.envelopes = []

    def handle(self, env) -> None:
        self.envelopes.append(env)


def _recorded_context(
    *sources, behavior_prompt="sys", workspace_root="ws"
) -> tuple[Context, "_Recorder"]:
    rec = _Recorder()
    scope = NullScope()
    scope.events = EventEmitter(sinks=[rec])
    ctx = Context(
        behavior_prompt=behavior_prompt,
        scope=scope,
        context_sources=list(sources),
        workspace_root=Path(workspace_root) if workspace_root else None,
    )
    return ctx, rec


def _call_requests(rec: "_Recorder") -> list[CallRequest]:
    return [e.event for e in rec.envelopes if isinstance(e.event, CallRequest)]


async def test_assemble_emits_one_call_request_per_call_even_without_sources():
    """The no-live-sources fast path is still an audited call."""
    ctx, rec = _recorded_context()  # zero live sources
    ctx.add(Message(role=Role.USER, content="hi"))

    await ctx.assemble()
    await ctx.assemble()

    reqs = _call_requests(rec)
    assert len(reqs) == 2
    assert reqs[0].projected == [(0, 1)]
    assert reqs[0].store_len == 1
    assert reqs[0].injected_run is None and reqs[0].injected_call is None


async def test_assemble_without_emitter_is_byte_identical():
    recorded, _rec = _recorded_context(_LiveSource(placement=Placement.RUN))
    bare = _live_context(_LiveSource(placement=Placement.RUN))
    recorded.add(Message(role=Role.USER, content="hi"))
    bare.add(Message(role=Role.USER, content="hi"))

    assert await recorded.assemble() == await bare.assemble()


async def test_injected_run_records_exact_appended_string_and_store_anchor():
    src = _LiveSource(name="gitStatus", placement=Placement.RUN)
    ctx, rec = _recorded_context(src)
    ctx.add(Message(role=Role.ASSISTANT, content="earlier"))
    ctx.add(Message(role=Role.USER, content="fix it"))

    msgs = await ctx.assemble()

    (req,) = _call_requests(rec)
    block = req.injected_run
    # anchor is a store index (the system message shifts assembled
    # positions by one, and the store holds two messages here).
    assert block.anchor == 1
    # text is exactly the string _merge_into_user appended, framing included.
    assert msgs[block.anchor + 1].content == f"fix it\n\n{block.text}"
    assert "<system-reminder>" in block.text
    assert req.injected_call is None


async def test_standalone_call_carrier_records_anchor_none():
    src = _LiveSource(name="watcher", placement=Placement.CALL)
    ctx, rec = _recorded_context(src)
    ctx.add(Message(role=Role.USER, content="go"))
    ctx.add(Message(role=Role.ASSISTANT, content="working"))
    ctx.add(Message(role=Role.TOOL, content="ok", tool_call_id="tc_1"))

    msgs = await ctx.assemble()

    (req,) = _call_requests(rec)
    assert req.injected_call.anchor is None
    # The carrier's full content, verbatim.
    assert msgs[-1].content == req.injected_call.text


async def test_failing_source_emits_source_failed_and_call_proceeds():
    bad = _LiveSource(name="bad", placement=Placement.RUN, raises=True)
    ctx, rec = _recorded_context(bad)
    ctx.add(Message(role=Role.USER, content="hi"))

    msgs = await ctx.assemble()

    failures = [e.event for e in rec.envelopes if isinstance(e.event, SourceFailed)]
    assert failures == [SourceFailed(source="bad", error="RuntimeError")]
    assert len(_call_requests(rec)) == 1
    assert msgs[-1].content == "hi"  # nothing injected, call proceeds


def _reconstruct(
    stored: list[Message], req: CallRequest, system_prompt: str | None
) -> list[Message]:
    """The audit recipe from the spec, applied to an in-memory store.

    The system prompt is a run-level fact (it rides run.start, not the
    call.request), so it's supplied here the way reconstruct_call() joins it
    from the run record."""
    msgs: list[Message] = []
    if system_prompt is not None:
        msgs.append(Message(role=Role.SYSTEM, content=system_prompt))
    for start, end in req.projected:
        msgs.extend(stored[start:end])

    offset = 1 if system_prompt is not None else 0
    if req.injected_run:
        i = req.injected_run.anchor + offset
        msgs[i] = _merge_into_user(msgs[i], req.injected_run.text)
    if req.injected_call:
        if req.injected_call.anchor is not None:
            i = req.injected_call.anchor + offset
            msgs[i] = _merge_into_user(msgs[i], req.injected_call.text)
        else:
            msgs.append(Message(role=Role.USER, content=req.injected_call.text))
    return msgs


_USER = Message(role=Role.USER, content="go")
_MULTIMODAL_USER = Message(role=Role.USER, content=[TextPart(text="look at this")])
_TOOL_ROUND = [
    Message(role=Role.ASSISTANT, content="working"),
    Message(role=Role.TOOL, content="ok", tool_call_id="tc_1"),
]


@pytest.mark.parametrize(
    ("placements", "stored"),
    [
        pytest.param([Placement.RUN], [_USER], id="run_only"),
        pytest.param([Placement.CALL], [_USER], id="call_only_first_call"),
        pytest.param([Placement.CALL], [_USER, *_TOOL_ROUND], id="call_only_carrier"),
        pytest.param([Placement.RUN, Placement.CALL], [_USER], id="run_and_call"),
        pytest.param([Placement.RUN], [_MULTIMODAL_USER], id="multimodal_anchor"),
        pytest.param([], [_USER], id="no_injection"),
    ],
)
async def test_round_trip_reconstruction_matches_hash(placements, stored):
    """Reconstruct per the audit recipe and verify against the recorded
    hash — for every injection shape."""
    sources = [
        _LiveSource(name=f"src{i}", placement=p) for i, p in enumerate(placements)
    ]
    ctx, rec = _recorded_context(*sources)
    for msg in stored:
        ctx.add(msg)
    ctx.begin_run()

    assembled = await ctx.assemble()

    (req,) = _call_requests(rec)
    rebuilt = _reconstruct(ctx.store.messages, req, ctx.system_prompt)
    assert hash_messages(rebuilt) == req.assembled_sha256
    assert rebuilt == assembled


# ---- lazy SESSION assembly (ensure_session_gathered) ------------------------


async def test_first_assemble_gathers_session_once_and_renders():
    src = _LiveSource(name="tree", placement=Placement.SESSION)
    ctx = _live_context(src)
    ctx.add(Message(role=Role.USER, content="hi"))

    first = await ctx.assemble()
    await ctx.assemble()
    ctx.begin_run()
    await ctx.assemble()

    assert src.calls == 1  # cached across assembles and runs
    system = first[0]
    assert system.role is Role.SYSTEM
    assert system.content.startswith("sys")
    assert "snapshot taken at first use" in system.content
    assert '<context name="tree">' in system.content
    assert "fresh data (gather 1)" in system.content


def test_get_messages_before_first_gather_is_behavior_prompt_alone():
    src = _LiveSource(name="tree", placement=Placement.SESSION)
    ctx = _live_context(src)
    ctx.add(Message(role=Role.USER, content="hi"))

    msgs = ctx.get_messages()

    assert src.calls == 0
    assert msgs[0].content == "sys"


async def test_preview_shares_snapshot_with_run():
    src = _LiveSource(name="tree", placement=Placement.SESSION)
    ctx = _live_context(src)

    await ctx.ensure_session_gathered()
    previewed = ctx.system_prompt

    assert "gather 1" in previewed
    ctx.add(Message(role=Role.USER, content="hi"))
    msgs = await ctx.assemble()
    assert src.calls == 1  # the preview and the run share one snapshot
    assert msgs[0].content == previewed


async def test_session_source_without_behavior_prompt_still_renders_system():
    src = _LiveSource(name="tree", placement=Placement.SESSION)
    scope = NullScope()
    ctx = Context(scope=scope, context_sources=[src], workspace_root=Path("ws"))
    ctx.add(Message(role=Role.USER, content="hi"))

    msgs = await ctx.assemble()

    assert msgs[0].role is Role.SYSTEM
    assert '<context name="tree">' in msgs[0].content


async def test_session_gather_is_fail_fast_and_retries():
    src = _LiveSource(name="boom", placement=Placement.SESSION, raises=True)
    ctx = _live_context(src)
    ctx.add(Message(role=Role.USER, content="hi"))

    with pytest.raises(RuntimeError):
        await ctx.assemble()

    # The failed gather must not half-populate the cache: the next
    # ensure retries the source instead of serving a broken snapshot.
    src._raises = False
    msgs = await ctx.assemble()
    assert src.calls == 2
    assert '<context name="boom">' in msgs[0].content


async def test_cancelled_first_gather_leaves_cache_ungathered():
    import asyncio

    release = asyncio.Event()
    started = asyncio.Event()

    class _BlockingSource:
        placement = Placement.SESSION
        name = "slow"
        calls = 0

        async def gather(self, workspace_root) -> str | None:
            type(self).calls += 1
            started.set()
            await release.wait()
            return "eventually"

    ctx = _live_context(_BlockingSource())
    task = asyncio.create_task(ctx.ensure_session_gathered())
    await started.wait()  # cancel mid-gather, not before it
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    release.set()
    await ctx.ensure_session_gathered()
    assert _BlockingSource.calls == 2
    assert "eventually" in ctx.system_prompt


async def test_no_session_sources_gathers_nothing_and_renders_behavior():
    ctx = Context(behavior_prompt="sys")
    await ctx.ensure_session_gathered()
    assert ctx.system_prompt == "sys"
