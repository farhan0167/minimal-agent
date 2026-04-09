"""Tests for `accumulate_tool_calls`.

OpenAI streams tool calls as fragments keyed by `index`: the first fragment
carries id+name, subsequent fragments carry incremental JSON string chunks
for `arguments`. The accumulator reassembles them. We simulate that by
building small async generators of hand-crafted StreamChunks.
"""

from typing import AsyncIterator, List

from minimal_agent.llm.llm import accumulate_tool_calls
from minimal_agent.llm.types import StreamChunk, ToolCallDelta


async def _gen(chunks: List[StreamChunk]) -> AsyncIterator[StreamChunk]:
    for c in chunks:
        yield c


class TestAccumulateToolCalls:
    async def test_empty_stream(self) -> None:
        text, calls = await accumulate_tool_calls(_gen([]))
        assert text == ""
        assert calls == []

    async def test_plain_text_chunks_concatenated(self) -> None:
        text, calls = await accumulate_tool_calls(
            _gen(
                [
                    StreamChunk(text="hello "),
                    StreamChunk(text="world"),
                    StreamChunk(text="!"),
                ]
            )
        )
        assert text == "hello world!"
        assert calls == []

    async def test_single_tool_call_reassembled_across_chunks(self) -> None:
        """First fragment carries id+name, later fragments carry argument
        string chunks that must be concatenated in order."""
        chunks = [
            StreamChunk(
                tool_calls=[ToolCallDelta(index=0, id="call_1", name="get_weather")]
            ),
            StreamChunk(tool_calls=[ToolCallDelta(index=0, arguments='{"city":')]),
            StreamChunk(tool_calls=[ToolCallDelta(index=0, arguments=' "NYC"}')]),
        ]
        text, calls = await accumulate_tool_calls(_gen(chunks))
        assert text == ""
        assert len(calls) == 1
        assert calls[0].id == "call_1"
        assert calls[0].name == "get_weather"
        assert calls[0].arguments == {"city": "NYC"}

    async def test_two_interleaved_tool_calls_stay_separated(self) -> None:
        """Different `index` values are distinct tool calls even when their
        fragments arrive interleaved in the stream."""
        chunks = [
            StreamChunk(tool_calls=[ToolCallDelta(index=0, id="c0", name="f0")]),
            StreamChunk(tool_calls=[ToolCallDelta(index=1, id="c1", name="f1")]),
            StreamChunk(tool_calls=[ToolCallDelta(index=0, arguments='{"a":')]),
            StreamChunk(tool_calls=[ToolCallDelta(index=1, arguments='{"b":')]),
            StreamChunk(tool_calls=[ToolCallDelta(index=0, arguments=" 1}")]),
            StreamChunk(tool_calls=[ToolCallDelta(index=1, arguments=" 2}")]),
        ]
        _, calls = await accumulate_tool_calls(_gen(chunks))
        assert len(calls) == 2
        # Result is sorted by index, so order is deterministic.
        assert calls[0].id == "c0"
        assert calls[0].name == "f0"
        assert calls[0].arguments == {"a": 1}
        assert calls[1].id == "c1"
        assert calls[1].name == "f1"
        assert calls[1].arguments == {"b": 2}

    async def test_fragment_with_no_id_is_dropped(self) -> None:
        """Can't form a valid ToolCall without an id — drop rather than raise."""
        chunks = [
            StreamChunk(
                tool_calls=[ToolCallDelta(index=0, arguments='{"orphan": true}')]
            ),
        ]
        _, calls = await accumulate_tool_calls(_gen(chunks))
        assert calls == []

    async def test_malformed_concatenated_json_falls_back_to_raw(self) -> None:
        chunks = [
            StreamChunk(tool_calls=[ToolCallDelta(index=0, id="c", name="f")]),
            StreamChunk(tool_calls=[ToolCallDelta(index=0, arguments="{bad")]),
        ]
        _, calls = await accumulate_tool_calls(_gen(chunks))
        assert calls[0].arguments == {"__raw__": "{bad"}

    async def test_text_and_tool_calls_mixed(self) -> None:
        """A realistic stream: some text, then a tool call fragmented across
        chunks. Both surfaces (text and calls) are populated."""
        chunks = [
            StreamChunk(text="let me check "),
            StreamChunk(text="the weather. "),
            StreamChunk(
                tool_calls=[ToolCallDelta(index=0, id="c", name="get_weather")]
            ),
            StreamChunk(
                tool_calls=[ToolCallDelta(index=0, arguments='{"city": "NYC"}')]
            ),
        ]
        text, calls = await accumulate_tool_calls(_gen(chunks))
        assert text == "let me check the weather. "
        assert len(calls) == 1
        assert calls[0].arguments == {"city": "NYC"}

    async def test_empty_arguments_become_empty_dict(self) -> None:
        """A tool call with no argument fragments — i.e. a zero-arg function —
        still reassembles into a valid ToolCall with arguments={}."""
        chunks = [
            StreamChunk(tool_calls=[ToolCallDelta(index=0, id="c", name="ping")]),
        ]
        _, calls = await accumulate_tool_calls(_gen(chunks))
        assert len(calls) == 1
        assert calls[0].arguments == {}
