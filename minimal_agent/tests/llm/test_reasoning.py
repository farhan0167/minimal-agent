"""Tests for reasoning ("thinking") support in the LLM facade.

Reasoning is non-standard across OpenAI-compatible providers: the request
toggle and the response field name are both provider-specific, declared once
via a ReasoningConfig. The facade merges the request knobs into the body,
reads the trace off the configured field, exposes a neutral `reasoning`
property, and — crucially — never replays a stored trace back to the model.

See the reasoning-support.md specification.

Stubs use SimpleNamespace to quack like SDK message/delta objects, same as
test_response_parsing.py / test_stream.py.
"""

from types import SimpleNamespace

import pytest

from minimal_agent.llm.llm import LLM, StreamAccumulator
from minimal_agent.llm.types import (
    Message,
    ReasoningConfig,
    Role,
    StreamChunk,
)


@pytest.fixture
def llm() -> LLM:
    return LLM(model="test-model", api_key="sk-test")


@pytest.fixture
def llm_reasoning() -> LLM:
    """An LLM configured for a Qwen-style provider."""
    return LLM(
        model="test-model",
        api_key="sk-test",
        reasoning=ReasoningConfig(
            request_params={"enable_thinking": True},
            response_field="reasoning_content",
        ),
    )


# ---- _extract_reasoning ----------------------------------------------------


class TestExtractReasoning:
    def test_returns_none_when_unconfigured(self, llm: LLM) -> None:
        obj = SimpleNamespace(reasoning_content="I thought about it")
        assert llm._extract_reasoning(obj) is None

    def test_reads_configured_field(self, llm_reasoning: LLM) -> None:
        obj = SimpleNamespace(reasoning_content="step by step")
        assert llm_reasoning._extract_reasoning(obj) == "step by step"

    def test_field_absent_returns_none(self, llm_reasoning: LLM) -> None:
        # Provider didn't emit the field on this object.
        assert llm_reasoning._extract_reasoning(SimpleNamespace()) is None

    def test_empty_string_normalizes_to_none(self, llm_reasoning: LLM) -> None:
        obj = SimpleNamespace(reasoning_content="")
        assert llm_reasoning._extract_reasoning(obj) is None

    def test_alternate_field_name(self, llm: LLM) -> None:
        # OpenRouter-style: trace comes back on `reasoning`.
        or_llm = LLM(
            model="m",
            api_key="sk-test",
            reasoning=ReasoningConfig(response_field="reasoning"),
        )
        obj = SimpleNamespace(reasoning="via openrouter")
        assert or_llm._extract_reasoning(obj) == "via openrouter"


# ---- request-param merge ---------------------------------------------------


class TestRequestParamMerge:
    def test_request_params_merged_into_body(self, llm_reasoning: LLM) -> None:
        params = llm_reasoning._completion_params(
            messages=[Message(role=Role.USER, content="hi")],
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
        # Reasoning knobs must ride extra_body, not top-level kwargs — a bare
        # `enable_thinking` kwarg is rejected by the SDK's typed create().
        assert "enable_thinking" not in params
        assert params["extra_body"] == {"enable_thinking": True}

    def test_per_call_extra_body_overrides_reasoning_params(self, llm: LLM) -> None:
        # Reasoning params land in extra_body; a per-call extra that ALSO sets
        # extra_body wins the collision (extra merges last, top-level).
        cfg_llm = LLM(
            model="m",
            api_key="sk-test",
            reasoning=ReasoningConfig(
                request_params={"reasoning_effort": "low"},
            ),
        )
        params = cfg_llm._completion_params(
            messages=[Message(role=Role.USER, content="hi")],
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
            extra={"extra_body": {"reasoning_effort": "high"}},
        )
        assert params["extra_body"] == {"reasoning_effort": "high"}

    def test_no_reasoning_leaves_body_clean(self, llm: LLM) -> None:
        params = llm._completion_params(
            messages=[Message(role=Role.USER, content="hi")],
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
        assert "enable_thinking" not in params
        assert "reasoning_effort" not in params
        assert "extra_body" not in params


# ---- strip-on-send invariant -----------------------------------------------


class TestStripOnSend:
    def test_reasoning_never_sent_to_model(self, llm_reasoning: LLM) -> None:
        # Even a message that carries a trace must not emit a `reasoning` key.
        msg = Message(
            role=Role.ASSISTANT,
            content="the answer",
            reasoning="my private chain of thought",
        )
        out = llm_reasoning._message_to_openai(msg)
        assert "reasoning" not in out
        assert out == {"role": "assistant", "content": "the answer"}


# ---- usage parsing ---------------------------------------------------------


class TestReasoningTokens:
    def test_parsed_from_details(self, llm: LLM) -> None:
        raw = SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=7),
        )
        usage = llm._parse_usage(raw)
        assert usage is not None
        assert usage.reasoning_tokens == 7

    def test_absent_details_leaves_none(self, llm: LLM) -> None:
        raw = SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        usage = llm._parse_usage(raw)
        assert usage is not None
        assert usage.reasoning_tokens is None


# ---- streaming accumulation ------------------------------------------------


class TestStreamAccumulatorReasoning:
    def test_concatenates_reasoning_deltas(self) -> None:
        acc = StreamAccumulator()
        acc.add(StreamChunk(reasoning="Let me "))
        acc.add(StreamChunk(text="answer: ", reasoning="think..."))
        acc.add(StreamChunk(text="42"))
        assert acc.reasoning == "Let me think..."
        assert acc.text == "answer: 42"

    def test_empty_when_no_reasoning(self) -> None:
        acc = StreamAccumulator()
        acc.add(StreamChunk(text="hi"))
        assert acc.reasoning == ""


# ---- with_reasoning helper -------------------------------------------------


class TestWithReasoning:
    def test_attaches_config_and_reuses_client(self, llm: LLM) -> None:
        cfg = ReasoningConfig(response_field="reasoning")
        clone = llm.with_reasoning(cfg)
        assert clone._reasoning is cfg
        # Reuses the underlying client rather than rebuilding it.
        assert clone.raw is llm.raw
        assert clone.model == llm.model
        assert clone.backend == llm.backend
        # Original is untouched.
        assert llm._reasoning is None
