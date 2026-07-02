from minimal_agent.agent.context import Context
from minimal_agent.agent.message_store import MessageStore
from minimal_agent.context_sources import Placement
from minimal_agent.llm.types import Message, Role, TextPart


def test_get_messages_with_system_prompt():
    ctx = Context(system_prompt="You are helpful.")
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
    ctx = Context(system_prompt="sys")
    ctx.add(Message(role=Role.USER, content="q"))

    assert len(ctx.get_messages()) == 2

    ctx.add(Message(role=Role.ASSISTANT, content="a"))

    assert len(ctx.get_messages()) == 3


def test_get_messages_is_pure():
    """Calling get_messages twice returns equivalent but distinct lists."""
    ctx = Context(system_prompt="sys")
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
    from pathlib import Path

    return Context(
        system_prompt="sys",
        store=store,
        live_sources=list(sources),
        workspace_root=Path(workspace_root) if workspace_root else None,
    )


def _no_consecutive_users(msgs: list[Message]) -> bool:
    return all(
        not (a.role is Role.USER and b.role is Role.USER)
        for a, b in zip(msgs, msgs[1:], strict=False)
    )


async def test_assemble_without_live_sources_equals_get_messages():
    ctx = Context(system_prompt="sys")
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
