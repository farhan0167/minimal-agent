"""Tests for `_parse_tool_calls` and `_parse_usage`.

The SDK returns nested objects (not dicts), so we use SimpleNamespace to
build stubs that quack like the real thing without importing OpenAI's
internal types.
"""

from types import SimpleNamespace

import pytest

from llm.llm import LLM


@pytest.fixture
def llm() -> LLM:
    return LLM(model="test-model", api_key="sk-test")


def _tc(id: str, name: str, arguments: str) -> SimpleNamespace:
    """Build a stub matching the shape of an SDK tool_call object."""
    return SimpleNamespace(
        id=id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


# ---- _parse_tool_calls -----------------------------------------------------


class TestParseToolCalls:
    def test_no_tool_calls_returns_none(self, llm: LLM) -> None:
        message = SimpleNamespace(tool_calls=None)
        assert llm._parse_tool_calls(message) is None

    def test_empty_tool_calls_returns_none(self, llm: LLM) -> None:
        message = SimpleNamespace(tool_calls=[])
        assert llm._parse_tool_calls(message) is None

    def test_missing_tool_calls_attr_returns_none(self, llm: LLM) -> None:
        """Some message shapes may not have the attribute at all."""
        message = SimpleNamespace()
        assert llm._parse_tool_calls(message) is None

    def test_arguments_json_string_parsed_to_dict(self, llm: LLM) -> None:
        message = SimpleNamespace(
            tool_calls=[_tc("call_1", "get_weather", '{"city": "NYC", "units": "F"}')]
        )
        parsed = llm._parse_tool_calls(message)
        assert parsed is not None
        assert len(parsed) == 1
        assert parsed[0].id == "call_1"
        assert parsed[0].name == "get_weather"
        assert parsed[0].arguments == {"city": "NYC", "units": "F"}

    def test_empty_arguments_string_becomes_empty_dict(self, llm: LLM) -> None:
        message = SimpleNamespace(tool_calls=[_tc("c", "f", "")])
        parsed = llm._parse_tool_calls(message)
        assert parsed[0].arguments == {}

    def test_malformed_json_falls_back_to_raw(self, llm: LLM) -> None:
        """Deliberate: the model occasionally emits bad JSON under pressure,
        and we'd rather surface the raw string than raise on the happy path."""
        message = SimpleNamespace(tool_calls=[_tc("c", "f", "{not valid json")])
        parsed = llm._parse_tool_calls(message)
        assert parsed[0].arguments == {"__raw__": "{not valid json"}

    def test_multiple_tool_calls_all_parsed(self, llm: LLM) -> None:
        message = SimpleNamespace(
            tool_calls=[
                _tc("c1", "f1", '{"a": 1}'),
                _tc("c2", "f2", '{"b": 2}'),
            ]
        )
        parsed = llm._parse_tool_calls(message)
        assert [p.name for p in parsed] == ["f1", "f2"]
        assert parsed[0].arguments == {"a": 1}
        assert parsed[1].arguments == {"b": 2}


# ---- _parse_usage ----------------------------------------------------------


class TestParseUsage:
    def test_none_returns_none(self, llm: LLM) -> None:
        """Streaming chunks omit usage unless include_usage is set."""
        assert llm._parse_usage(None) is None

    def test_populated_usage(self, llm: LLM) -> None:
        raw = SimpleNamespace(
            prompt_tokens=10, completion_tokens=20, total_tokens=30
        )
        usage = llm._parse_usage(raw)
        assert usage is not None
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 20
        assert usage.total_tokens == 30

    def test_missing_fields_default_to_zero(self, llm: LLM) -> None:
        raw = SimpleNamespace()
        usage = llm._parse_usage(raw)
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_none_valued_fields_default_to_zero(self, llm: LLM) -> None:
        """Some backends report the field as present-but-None."""
        raw = SimpleNamespace(
            prompt_tokens=None, completion_tokens=None, total_tokens=None
        )
        usage = llm._parse_usage(raw)
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0
