"""Tests for the request-building helpers on `LLM`.

These are pure functions — struct in, dict out — so we instantiate `LLM`
with a dummy api key and call the private helpers directly. No network,
no mocks.
"""

import json

import pytest

from llm.llm import LLM
from llm.types import ImagePart, ImageUrl, LLMTool, Message, TextPart, ToolCall


@pytest.fixture
def llm() -> LLM:
    # api_key is required by AsyncOpenAI's constructor but we never call the
    # network in these tests, so any non-empty string works.
    return LLM(model="test-model", api_key="sk-test")


# ---- _message_to_openai ----------------------------------------------------


class TestMessageToOpenAI:
    def test_plain_user_message(self, llm: LLM) -> None:
        out = llm._message_to_openai(Message(role="user", content="hello"))
        assert out == {"role": "user", "content": "hello"}

    def test_assistant_with_only_tool_calls_omits_content(self, llm: LLM) -> None:
        msg = Message(
            role="assistant",
            content=None,
            tool_calls=[
                ToolCall(id="call_1", name="get_weather", arguments={"city": "NYC"})
            ],
        )
        out = llm._message_to_openai(msg)
        assert "content" not in out
        assert out["role"] == "assistant"
        assert out["tool_calls"] == [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": json.dumps({"city": "NYC"}),
                },
            }
        ]

    def test_tool_call_arguments_serialized_as_json_string(self, llm: LLM) -> None:
        """Neutral shape stores arguments as dict; wire format is a JSON string."""
        msg = Message(
            role="assistant",
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="f",
                    arguments={"nested": {"a": 1}, "list": [1, 2]},
                )
            ],
        )
        out = llm._message_to_openai(msg)
        args_str = out["tool_calls"][0]["function"]["arguments"]
        assert isinstance(args_str, str)
        assert json.loads(args_str) == {"nested": {"a": 1}, "list": [1, 2]}

    def test_tool_result_message(self, llm: LLM) -> None:
        msg = Message(
            role="tool",
            content="72 degrees",
            tool_call_id="call_1",
        )
        out = llm._message_to_openai(msg)
        assert out == {
            "role": "tool",
            "content": "72 degrees",
            "tool_call_id": "call_1",
        }

    def test_multimodal_content_parts_dumped_to_dicts(self, llm: LLM) -> None:
        msg = Message(
            role="user",
            content=[
                TextPart(text="what's this?"),
                ImagePart(image_url=ImageUrl(url="https://example.com/x.png")),
            ],
        )
        out = llm._message_to_openai(msg)
        assert out["content"] == [
            {"type": "text", "text": "what's this?"},
            {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
        ]

    def test_multimodal_image_detail_included_when_set(self, llm: LLM) -> None:
        msg = Message(
            role="user",
            content=[
                ImagePart(image_url=ImageUrl(url="https://x/y.png", detail="high"))
            ],
        )
        out = llm._message_to_openai(msg)
        assert out["content"][0]["image_url"]["detail"] == "high"


# ---- _build_messages -------------------------------------------------------


class TestBuildMessages:
    def test_system_prompt_prepended(self, llm: LLM) -> None:
        out = llm._build_messages(
            [Message(role="user", content="hi")],
            system="you are helpful",
        )
        assert out[0] == {"role": "system", "content": "you are helpful"}
        assert out[1] == {"role": "user", "content": "hi"}

    def test_no_system_prompt(self, llm: LLM) -> None:
        out = llm._build_messages([Message(role="user", content="hi")], system=None)
        assert len(out) == 1
        assert out[0]["role"] == "user"


# ---- _build_tools ----------------------------------------------------------


class TestBuildTools:
    def test_wraps_in_function_envelope(self, llm: LLM) -> None:
        tool = LLMTool(
            name="get_weather",
            description="Look up the weather",
            parameters={
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        )
        out = llm._build_tools([tool])
        assert out == [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Look up the weather",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }
        ]


# ---- _normalize_tool_choice ------------------------------------------------


class TestNormalizeToolChoice:
    def test_none_passes_through(self, llm: LLM) -> None:
        assert llm._normalize_tool_choice(None) is None

    @pytest.mark.parametrize("mode", ["auto", "none", "required"])
    def test_string_modes_pass_through(self, llm: LLM, mode: str) -> None:
        assert llm._normalize_tool_choice(mode) == mode

    def test_bare_tool_name_wraps_in_forced_call_envelope(self, llm: LLM) -> None:
        assert llm._normalize_tool_choice("get_weather") == {
            "type": "function",
            "function": {"name": "get_weather"},
        }


# ---- _completion_params ----------------------------------------------------


def _params(llm: LLM, **overrides):
    """Call `_completion_params` with defaults, overriding only what's asked."""
    defaults = dict(
        messages=[Message(role="user", content="hi")],
        system=None,
        tools=None,
        tool_choice=None,
        parallel_tool_calls=None,
        response_format=None,
        max_tokens=None,
        temperature=None,
        top_p=None,
        frequency_penalty=None,
        presence_penalty=None,
        stop=None,
        n=None,
        seed=None,
        logprobs=None,
        top_logprobs=None,
        user=None,
        extra=None,
    )
    defaults.update(overrides)
    return llm._completion_params(**defaults)


class TestCompletionParams:
    def test_minimal_params_only_include_model_and_messages(self, llm: LLM) -> None:
        params = _params(llm)
        assert set(params.keys()) == {"model", "messages"}
        assert params["model"] == "test-model"

    def test_none_values_are_omitted(self, llm: LLM) -> None:
        """Critical: None params must not be forwarded — provider defaults
        depend on the key being absent, not explicitly None."""
        params = _params(llm)
        forbidden = {
            "temperature",
            "top_p",
            "max_completion_tokens",
            "max_tokens",
            "stop",
            "seed",
            "n",
            "frequency_penalty",
            "presence_penalty",
            "logprobs",
            "top_logprobs",
            "user",
            "response_format",
            "tools",
            "tool_choice",
            "parallel_tool_calls",
        }
        assert forbidden.isdisjoint(params.keys())

    def test_max_tokens_renamed_to_max_completion_tokens(self, llm: LLM) -> None:
        """`max_tokens` is deprecated and reasoning models reject it."""
        params = _params(llm, max_tokens=256)
        assert "max_tokens" not in params
        assert params["max_completion_tokens"] == 256

    def test_scalar_params_forwarded_when_set(self, llm: LLM) -> None:
        params = _params(
            llm,
            temperature=0.7,
            top_p=0.9,
            frequency_penalty=0.1,
            presence_penalty=0.2,
            seed=42,
            n=2,
            user="u-1",
            stop=["\n\n"],
        )
        assert params["temperature"] == 0.7
        assert params["top_p"] == 0.9
        assert params["frequency_penalty"] == 0.1
        assert params["presence_penalty"] == 0.2
        assert params["seed"] == 42
        assert params["n"] == 2
        assert params["user"] == "u-1"
        assert params["stop"] == ["\n\n"]

    def test_tools_block_not_emitted_without_tools(self, llm: LLM) -> None:
        """tool_choice / parallel_tool_calls are only meaningful alongside tools."""
        params = _params(llm, tool_choice="auto", parallel_tool_calls=True)
        assert "tools" not in params
        assert "tool_choice" not in params
        assert "parallel_tool_calls" not in params

    def test_tools_block_emitted_with_tools(self, llm: LLM) -> None:
        tool = LLMTool(name="f", description="d")
        params = _params(llm, tools=[tool], tool_choice="f", parallel_tool_calls=False)
        assert params["tools"][0]["function"]["name"] == "f"
        assert params["tool_choice"] == {
            "type": "function",
            "function": {"name": "f"},
        }
        assert params["parallel_tool_calls"] is False

    def test_extra_passthrough_merges_last(self, llm: LLM) -> None:
        params = _params(llm, extra={"custom_field": "x", "temperature": 0.5})
        assert params["custom_field"] == "x"
        # extra wins over anything set earlier
        assert params["temperature"] == 0.5
