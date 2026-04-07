from agent.context import Context
from llm.types import Message, Role


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
