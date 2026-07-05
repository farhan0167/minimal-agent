"""Tests for `LLM.stream()` chunk parsing.

Providers disagree on where usage rides in a stream when
`stream_options.include_usage` is set: OpenAI sends a dedicated trailing
chunk with an empty `choices` list, while OpenRouter (and other compat
providers) attach usage to the final content chunk, which still carries a
choice. The facade must surface both, or `on_usage` silently never fires
for the second family — session usage stays null with no error anywhere.

Stubs use SimpleNamespace to quack like SDK chunk objects, same as
test_response_parsing.py.
"""

from types import SimpleNamespace

import pytest

from minimal_agent.llm.llm import LLM

_USAGE = SimpleNamespace(prompt_tokens=18, completion_tokens=10, total_tokens=28)


def _content_chunk(text, finish_reason=None, usage=None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=text, tool_calls=None),
                finish_reason=finish_reason,
            )
        ],
        usage=usage,
    )


def _usage_only_chunk(usage) -> SimpleNamespace:
    """OpenAI's trailing usage chunk: empty choices, usage set."""
    return SimpleNamespace(choices=[], usage=usage)


def _llm_streaming(events) -> LLM:
    """An LLM whose client streams the given stub events."""
    llm = LLM(model="test-model", api_key="sk-test")

    async def _create(**_params):
        async def _iter():
            for event in events:
                yield event

        return _iter()

    llm._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )
    return llm


async def _collect(llm: LLM) -> list:
    return [chunk async for chunk in llm.stream(messages=[])]


class TestStreamUsage:
    async def test_openai_shape_usage_on_trailing_empty_choices_chunk(self) -> None:
        llm = _llm_streaming(
            [
                _content_chunk("hi"),
                _content_chunk("", finish_reason="stop"),
                _usage_only_chunk(_USAGE),
            ]
        )
        chunks = await _collect(llm)
        with_usage = [c for c in chunks if c.usage]
        assert len(with_usage) == 1
        assert with_usage[0].usage.total_tokens == 28

    async def test_openrouter_shape_usage_on_final_content_chunk(self) -> None:
        """Usage attached to a chunk that still has a choice must not be
        dropped — this is OpenRouter's shape."""
        llm = _llm_streaming(
            [
                _content_chunk("hi"),
                _content_chunk("", finish_reason="stop", usage=_USAGE),
            ]
        )
        chunks = await _collect(llm)
        with_usage = [c for c in chunks if c.usage]
        assert len(with_usage) == 1
        assert with_usage[0].usage.prompt_tokens == 18
        assert with_usage[0].usage.completion_tokens == 10
        assert with_usage[0].finish_reason == "stop"

    async def test_no_usage_anywhere_yields_no_usage_chunks(self) -> None:
        llm = _llm_streaming(
            [
                _content_chunk("hi"),
                _content_chunk("", finish_reason="stop"),
            ]
        )
        chunks = await _collect(llm)
        assert all(c.usage is None for c in chunks)

    async def test_text_deltas_unaffected_by_usage_parsing(self) -> None:
        llm = _llm_streaming(
            [
                _content_chunk("hel"),
                _content_chunk("lo", finish_reason="stop", usage=_USAGE),
            ]
        )
        chunks = await _collect(llm)
        assert "".join(c.text for c in chunks) == "hello"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Belt and braces: these tests must never hit the network."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
