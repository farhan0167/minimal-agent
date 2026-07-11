"""LLM facade — a thin async wrapper over the OpenAI chat completions client.

    from minimal_agent.llm import LLM, Message

    llm = LLM(model="gpt-4o-mini")
    resp = await llm.generate([Message(role=Role.USER, content="hi")])
    print(resp.text)

Streaming:

    async for chunk in llm.stream([...]):
        print(chunk.text, end="", flush=True)

Tool calling:

    tools = [LLMTool(name="get_weather", description="...", parameters={...})]
    resp = await llm.generate(messages, tools=tools)
    if resp.tool_calls:
        for tc in resp.tool_calls:
            result = run_tool(tc.name, tc.arguments)
            messages.append(assistant_message_from(resp))
            messages.append(Message(role=Role.TOOL, tool_call_id=tc.id, content=result))

Escape hatch to the raw SDK client for features we haven't surfaced:

    await llm.raw.chat.completions.create(...)
"""

import json
from typing import (
    Any,
    AsyncIterator,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from openai import AsyncOpenAI
from pydantic import BaseModel

from ..config import Backend, settings
from .types import (
    GenerateResponse,
    LLMTool,
    Message,
    ReasoningConfig,
    ReasoningEffort,
    StreamChunk,
    StructuredResponse,
    ToolCall,
    ToolCallDelta,
    Usage,
)

T = TypeVar("T", bound=BaseModel)

# Type for the `tool_choice` argument. Accepts OpenAI's string modes
# ("auto", "none", "required") or a tool name to force a specific call.
ToolChoice = str

_BACKEND_BASE_URLS: Dict[Backend, str] = {
    Backend.OPENROUTER: "https://openrouter.ai/api/v1",
    Backend.ANTHROPIC: "https://api.anthropic.com/v1/",
}


class LLM:
    def __init__(
        self,
        model: str,
        *,
        backend: Backend = Backend.OPENAI,
        reasoning_config: Optional[ReasoningConfig] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        default_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.model = model
        self.backend: Backend = backend
        self._reasoning_config = reasoning_config
        client_kwargs: Dict[str, Any] = {}
        if api_key is not None:
            client_kwargs["api_key"] = api_key
        if base_url is not None:
            client_kwargs["base_url"] = base_url
        if timeout is not None:
            client_kwargs["timeout"] = timeout
        if max_retries is not None:
            client_kwargs["max_retries"] = max_retries
        if default_headers is not None:
            client_kwargs["default_headers"] = default_headers
        self._apply_backend_defaults(client_kwargs)
        self._client = AsyncOpenAI(**client_kwargs)

    def _apply_backend_defaults(
        self,
        client_kwargs: Dict[str, Any],
    ) -> None:
        """Mutate *client_kwargs* with sensible defaults for the backend.

        Reads the api_key and optional headers from settings, sets the
        provider's base_url, and injects OpenRouter's leaderboard headers.
        """
        if "api_key" not in client_kwargs:
            client_kwargs["api_key"] = settings.LLM_BACKEND_API_KEY or (
                "not-needed" if self.backend == Backend.LOCALHOST else None
            )

        if settings.LLM_BACKEND_BASE_URL:
            client_kwargs.setdefault("base_url", settings.LLM_BACKEND_BASE_URL)
        elif self.backend in _BACKEND_BASE_URLS:
            client_kwargs.setdefault("base_url", _BACKEND_BASE_URLS[self.backend])

        if self.backend == Backend.OPENROUTER:
            site_url = settings.LLM_BACKEND_SITE_URL
            app_name = settings.LLM_BACKEND_APP_NAME
            if site_url or app_name:
                headers: Dict[str, str] = {}
                if site_url:
                    headers["HTTP-Referer"] = site_url
                if app_name:
                    headers["X-Title"] = app_name
                existing = client_kwargs.get("default_headers") or {}
                client_kwargs["default_headers"] = {
                    **headers,
                    **existing,
                }

    @property
    def raw(self) -> AsyncOpenAI:
        return self._client

    def construct_with_reasoning(self, reasoning_config: ReasoningConfig) -> "LLM":
        """Return this client configured to request/read reasoning traces.

        Cheap: reuses the underlying AsyncOpenAI client rather than rebuilding
        it. `Agent` uses this to attach its reasoning config to a bare LLM.
        """
        clone = object.__new__(LLM)
        clone.model = self.model
        clone.backend = self.backend
        clone._reasoning_config = reasoning_config
        clone._client = self._client
        return clone

    def _extract_reasoning(self, obj: Any, reasoning: bool = True) -> Optional[str]:
        """Read the provider's reasoning trace off an SDK message/delta.

        The field name is configured (reasoning_content | reasoning | ...),
        never hardcoded. Returns None when reasoning wasn't requested for this
        call (`reasoning=False`), reasoning is not configured, or the provider
        didn't emit the field on this object.
        """
        if not reasoning or self._reasoning_config is None:
            return None
        return getattr(obj, self._reasoning_config.response_field, None) or None

    # ---- request building --------------------------------------------------

    def _message_to_openai(self, m: Message) -> Dict[str, Any]:
        """Translate a neutral Message into the dict the OpenAI SDK expects.

        The non-obvious parts:
        - Assistant messages with tool_calls must wrap each call in
          {id, type:"function", function:{name, arguments:<JSON string>}}.
          Our neutral shape stores `arguments` as a dict for ergonomics, so
          we json.dumps on the way out.
        - Tool result messages (role=Role.TOOL) need tool_call_id and a string
          content.
        - Multimodal content is a list of parts (text / image_url); each part
          is a Pydantic model and needs to be dumped to a plain dict for the
          SDK.
        """
        out: Dict[str, Any] = {"role": m.role}
        if m.content is not None:
            if isinstance(m.content, list):
                out["content"] = [
                    part.model_dump(exclude_none=True) for part in m.content
                ]
            else:
                out["content"] = m.content
        # NOTE: m.reasoning is intentionally NOT emitted. It is persisted for
        # display/audit but never replayed to the model — most providers reject
        # a `reasoning` key on input messages, and re-sending prior thinking is
        # wasteful. See reasoning-support.md (strip-on-send invariant).
        if m.tool_call_id is not None:
            out["tool_call_id"] = m.tool_call_id
        if m.tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in m.tool_calls
            ]
        return out

    def _build_messages(
        self, messages: List[Message], system: Optional[str]
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if system:
            out.append({"role": "system", "content": system})
        for m in messages:
            out.append(self._message_to_openai(m))
        return out

    def _build_tools(self, tools: List[LLMTool]) -> List[Dict[str, Any]]:
        """Wrap each neutral LLMTool in OpenAI's {"type":"function", ...} envelope."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def _normalize_tool_choice(
        self, tool_choice: Optional[ToolChoice]
    ) -> Union[str, Dict[str, Any], None]:
        """Translate our ergonomic tool_choice into OpenAI's shape.

        OpenAI accepts either a string mode ("auto" | "none" | "required")
        or an object {"type":"function","function":{"name":"..."}} to force
        a specific tool. We accept any of those, plus the shorthand of
        passing a bare tool name as a string.
        """
        if tool_choice is None:
            return None
        if tool_choice in ("auto", "none", "required"):
            return tool_choice
        # Bare tool name — wrap in OpenAI's forced-call envelope.
        return {"type": "function", "function": {"name": tool_choice}}

    def _completion_params(
        self,
        messages: List[Message],
        system: Optional[str],
        tools: Optional[List[LLMTool]],
        tool_choice: Optional[ToolChoice],
        parallel_tool_calls: Optional[bool],
        response_format: Optional[Dict[str, Any]],
        max_tokens: Optional[int],
        temperature: Optional[float],
        top_p: Optional[float],
        frequency_penalty: Optional[float],
        presence_penalty: Optional[float],
        stop: Union[str, List[str], None],
        n: Optional[int],
        seed: Optional[int],
        logprobs: Optional[bool],
        top_logprobs: Optional[int],
        user: Optional[str],
        extra: Optional[Dict[str, Any]],
        reasoning: bool = True,
        effort: Optional[ReasoningEffort] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(messages, system),
        }
        if tools:
            params["tools"] = self._build_tools(tools)
            normalized_choice = self._normalize_tool_choice(tool_choice)
            if normalized_choice is not None:
                params["tool_choice"] = normalized_choice
            if parallel_tool_calls is not None:
                params["parallel_tool_calls"] = parallel_tool_calls
        if max_tokens is not None:
            # `max_tokens` is deprecated; reasoning models reject it outright.
            params["max_completion_tokens"] = max_tokens
        if temperature is not None:
            params["temperature"] = temperature
        if top_p is not None:
            params["top_p"] = top_p
        if frequency_penalty is not None:
            params["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            params["presence_penalty"] = presence_penalty
        if stop is not None:
            params["stop"] = stop
        if n is not None:
            params["n"] = n
        if seed is not None:
            params["seed"] = seed
        if logprobs is not None:
            params["logprobs"] = logprobs
        if top_logprobs is not None:
            params["top_logprobs"] = top_logprobs
        if user is not None:
            params["user"] = user
        if response_format is not None:
            params["response_format"] = response_format
        if reasoning and self._reasoning_config is not None:
            # Reasoning knobs go through `extra_body`, NOT as top-level kwargs.
            # The SDK only forwards keys it doesn't model when they're nested
            # under extra_body; a bare kwarg like `enable_thinking` is rejected
            # by create()'s typed signature before it reaches the wire. Native
            # keys (e.g. reasoning_effort) reach the server identically this way,
            # so one rule covers every provider — no native/extension guessing.
            body = {
                **(params.get("extra_body") or {}),
                **self._reasoning_config.request_params,
            }
            if effort is not None:
                body[self._reasoning_config.effort_param] = effort
            if body:
                params["extra_body"] = body
        if extra:
            # Last-resort passthrough for anything we haven't surfaced.
            params.update(extra)
        return params

    # ---- response parsing --------------------------------------------------

    def _parse_usage(self, raw_usage: Any) -> Optional[Usage]:
        """Convert an SDK usage object into our neutral Usage model.

        Streaming responses omit usage unless `stream_options.include_usage`
        was set, so this returns None when the field is missing.
        """
        if raw_usage is None:
            return None
        details = getattr(raw_usage, "completion_tokens_details", None)
        return Usage(
            prompt_tokens=getattr(raw_usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(raw_usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(raw_usage, "total_tokens", 0) or 0,
            reasoning_tokens=(
                getattr(details, "reasoning_tokens", None) if details else None
            ),
        )

    def _parse_tool_calls(self, message: Any) -> Optional[List[ToolCall]]:
        """Pull tool_calls off an OpenAI assistant message and parse arguments.

        OpenAI returns `arguments` as a JSON-encoded string; we json.loads it
        into a dict so call sites don't each have to. If parsing fails we
        leave the raw string wrapped in a single-key dict rather than raising,
        since the model occasionally emits malformed JSON under pressure.
        """
        raw_calls = getattr(message, "tool_calls", None)
        if not raw_calls:
            return None
        parsed: List[ToolCall] = []
        for tc in raw_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"__raw__": tc.function.arguments}
            parsed.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return parsed

    # ---- public API --------------------------------------------------------

    async def generate(
        self,
        messages: List[Message],
        *,
        system: Optional[str] = None,
        tools: Optional[List[LLMTool]] = None,
        tool_choice: Optional[ToolChoice] = None,
        parallel_tool_calls: Optional[bool] = None,
        response_format: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        stop: Union[str, List[str], None] = None,
        n: Optional[int] = None,
        seed: Optional[int] = None,
        logprobs: Optional[bool] = None,
        top_logprobs: Optional[int] = None,
        user: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
        reasoning: bool = True,
        effort: Optional[ReasoningEffort] = None,
    ) -> GenerateResponse:
        completion = await self._client.chat.completions.create(
            **self._completion_params(
                messages=messages,
                system=system,
                tools=tools,
                tool_choice=tool_choice,
                parallel_tool_calls=parallel_tool_calls,
                response_format=response_format,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                stop=stop,
                n=n,
                seed=seed,
                logprobs=logprobs,
                top_logprobs=top_logprobs,
                user=user,
                extra=extra,
                reasoning=reasoning,
                effort=effort,
            )
        )
        choice = completion.choices[0]
        return GenerateResponse(
            text=choice.message.content or "",
            reasoning=self._extract_reasoning(choice.message, reasoning),
            tool_calls=self._parse_tool_calls(choice.message),
            finish_reason=choice.finish_reason,
            usage=self._parse_usage(getattr(completion, "usage", None)),
            raw=completion,
        )

    async def generate_structured(
        self,
        messages: List[Message],
        *,
        schema: Type[T],
        system: Optional[str] = None,
        tools: Optional[List[LLMTool]] = None,
        tool_choice: Optional[ToolChoice] = None,
        parallel_tool_calls: Optional[bool] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        stop: Union[str, List[str], None] = None,
        seed: Optional[int] = None,
        user: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
        reasoning: bool = True,
        effort: Optional[ReasoningEffort] = None,
    ) -> StructuredResponse[T]:
        """Generate a response parsed into a Pydantic model.

        Uses the SDK's `chat.completions.parse` helper, which wraps the
        Pydantic model as a strict json_schema `response_format` and validates
        the assistant's reply back into an instance of `schema`.

        Backend compatibility: requires the server to honor
        `response_format: {"type":"json_schema", "strict": true}`. OpenAI and
        vLLM support this well; llama.cpp supports it via grammars; Ollama's
        /v1 endpoint does not honor json_schema reliably — callers targeting
        Ollama should prompt-engineer JSON and parse manually instead.

        `n`, `logprobs`, `top_logprobs`, and `response_format` are intentionally
        not exposed here: `parse` owns `response_format`, and structured outputs
        only return a single choice.
        """
        params = self._completion_params(
            messages=messages,
            system=system,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            response_format=None,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            stop=stop,
            n=None,
            seed=seed,
            logprobs=None,
            top_logprobs=None,
            user=user,
            extra=extra,
            reasoning=reasoning,
            effort=effort,
        )
        # `parse` takes `response_format` as a Pydantic class directly and
        # handles the json_schema wrapping + client-side validation itself.
        params["response_format"] = schema
        completion = await self._client.chat.completions.parse(**params)
        choice = completion.choices[0]
        message = choice.message
        return StructuredResponse[T](
            text=message.content or "",
            reasoning=self._extract_reasoning(message, reasoning),
            parsed=getattr(message, "parsed", None),
            refusal=getattr(message, "refusal", None),
            finish_reason=choice.finish_reason,
            usage=self._parse_usage(getattr(completion, "usage", None)),
            raw=completion,
        )

    async def stream(
        self,
        messages: List[Message],
        *,
        system: Optional[str] = None,
        tools: Optional[List[LLMTool]] = None,
        tool_choice: Optional[ToolChoice] = None,
        parallel_tool_calls: Optional[bool] = None,
        response_format: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        stop: Union[str, List[str], None] = None,
        n: Optional[int] = None,
        seed: Optional[int] = None,
        logprobs: Optional[bool] = None,
        top_logprobs: Optional[int] = None,
        user: Optional[str] = None,
        include_usage: bool = True,
        extra: Optional[Dict[str, Any]] = None,
        reasoning: bool = True,
        effort: Optional[ReasoningEffort] = None,
    ) -> AsyncIterator[StreamChunk]:
        params = self._completion_params(
            messages=messages,
            system=system,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            response_format=response_format,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            stop=stop,
            n=n,
            seed=seed,
            logprobs=logprobs,
            top_logprobs=top_logprobs,
            user=user,
            extra=extra,
            reasoning=reasoning,
            effort=effort,
        )
        params["stream"] = True
        if include_usage:
            # Ask the server to emit a final chunk carrying token usage.
            # Without this, streaming responses never include usage info.
            params["stream_options"] = {"include_usage": True}
        async for event in await self._client.chat.completions.create(**params):
            # The final usage chunk has an empty `choices` list; surface it as
            # a StreamChunk with usage set instead of skipping it.
            if not event.choices:
                usage = self._parse_usage(getattr(event, "usage", None))
                if usage is not None:
                    yield StreamChunk(usage=usage, raw=event)
                continue
            choice = event.choices[0]
            delta = choice.delta
            tool_call_deltas: Optional[List[ToolCallDelta]] = None
            raw_tcs = getattr(delta, "tool_calls", None)
            if raw_tcs:
                tool_call_deltas = [
                    ToolCallDelta(
                        index=tc.index,
                        id=tc.id,
                        name=tc.function.name if tc.function else None,
                        arguments=tc.function.arguments if tc.function else None,
                    )
                    for tc in raw_tcs
                ]
            yield StreamChunk(
                text=delta.content or "",
                reasoning=self._extract_reasoning(delta, reasoning) or "",
                tool_calls=tool_call_deltas,
                finish_reason=choice.finish_reason,
                # OpenAI sends usage as a dedicated trailing chunk with empty
                # choices (handled above), but OpenRouter and other compat
                # providers attach it to the final content chunk — parse it
                # here too or those providers never report usage.
                usage=self._parse_usage(getattr(event, "usage", None)),
                raw=event,
            )


class StreamAccumulator:
    """Folds streamed `StreamChunk`s back into text + completed tool calls.

    OpenAI streams tool call arguments as incremental JSON string fragments
    keyed by `index`; the first fragment for an index carries id and name,
    subsequent fragments carry argument chunks that must be concatenated. This
    object owns that bookkeeping so callers can either fully consume a stream
    in one shot (`accumulate_tool_calls`) or feed chunks one at a time while
    still emitting live deltas (the agent loop's streaming path).
    """

    def __init__(self) -> None:
        self._text_parts: List[str] = []
        self._reasoning_parts: List[str] = []
        # index -> {id, name, arguments_str}
        self._acc: Dict[int, Dict[str, Any]] = {}

    def add(self, chunk: StreamChunk) -> None:
        """Fold a single chunk into the running state."""
        if chunk.text:
            self._text_parts.append(chunk.text)
        if chunk.reasoning:
            self._reasoning_parts.append(chunk.reasoning)
        if chunk.tool_calls:
            for tcd in chunk.tool_calls:
                slot = self._acc.setdefault(
                    tcd.index, {"id": None, "name": None, "arguments": ""}
                )
                if tcd.id:
                    slot["id"] = tcd.id
                if tcd.name:
                    slot["name"] = tcd.name
                if tcd.arguments:
                    slot["arguments"] += tcd.arguments

    @property
    def text(self) -> str:
        return "".join(self._text_parts)

    @property
    def reasoning(self) -> str:
        return "".join(self._reasoning_parts)

    def tool_calls(self) -> List[ToolCall]:
        """Build the completed tool calls from accumulated fragments.

        Slots missing an id or name never received their opening fragment and
        are dropped. Malformed argument JSON is wrapped rather than raised,
        since models occasionally emit bad JSON under pressure.
        """
        calls: List[ToolCall] = []
        for index in sorted(self._acc):
            slot = self._acc[index]
            if slot["id"] is None or slot["name"] is None:
                continue
            try:
                args = json.loads(slot["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {"__raw__": slot["arguments"]}
            calls.append(ToolCall(id=slot["id"], name=slot["name"], arguments=args))
        return calls


async def accumulate_tool_calls(
    chunks: AsyncIterator[StreamChunk],
) -> Tuple[str, List[ToolCall]]:
    """Consume a stream and reassemble text + completed tool calls.

    A convenience wrapper over `StreamAccumulator` for call sites that don't
    need live deltas and can treat streaming as "generate, but yielding text
    as it arrives."
    """
    acc = StreamAccumulator()
    async for chunk in chunks:
        acc.add(chunk)
    return acc.text, acc.tool_calls()
