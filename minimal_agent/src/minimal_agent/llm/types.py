"""Request/response types for the LLM facade.

Thin wrappers around what OpenAI's chat completions API speaks, kept as
Pydantic models so call sites get validation and autocompletion without
touching the SDK's typed dicts directly.
"""

from enum import StrEnum
from typing import Any, Dict, Generic, List, Literal, Optional, Type, TypeVar, Union

from openai import pydantic_function_tool
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T", bound=BaseModel)


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


# The neutral vocabulary of reasoning effort levels the framework knows about,
# borrowed verbatim from OpenAI's `reasoning_effort` set. This is a library
# artifact — a fixed enumeration of levels — not a provider contract. The value
# passes through to the request unchanged; `ReasoningConfig.effort_param` only
# says WHICH key in the body carries it. See per-run-reasoning-toggle.md.
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]


class ReasoningConfig(BaseModel):
    """How reasoning is requested from, and read back off, a provider.

    Reasoning ("thinking") is non-standard across OpenAI-compatible providers,
    so the caller declares the provider's contract once at Agent-definition
    time. Whether reasoning is actually requested is a per-run decision made at
    `agent.run()` / the LLM facade — this object is only the contract for how.
    See the per-run-reasoning-toggle.md specification for the full design.

    - `request_params`: the static, NON-effort request-side knobs, merged
      verbatim into the body — the on-switch and any always-on options
      (Qwen's `enable_thinking: true`). Do NOT put effort here; effort is
      per-run and lands on `effort_param`. The SDK forwards unknown keys via
      `extra_body`, so we don't distinguish.
    - `response_field`: the (extra, non-standard) attribute the trace comes back
      on. "reasoning_content" for Qwen/DeepSeek, "reasoning" for OpenRouter.
      Read defensively with getattr — absent on providers that don't reason.
    - `effort_param`: the flat request key the per-run effort level is written
      to. The default is OpenAI's native `reasoning_effort`, which OpenRouter
      also accepts as a first-class alias of `reasoning.effort` — so the named
      backends need no override. Set it only when the server behind the
      backend expects a different key (a LOCALHOST dialect).
    """

    request_params: Dict[str, Any] = Field(default_factory=dict)
    response_field: str = "reasoning_content"
    effort_param: str = "reasoning_effort"


class TextPart(BaseModel):
    """A text segment in a multimodal message."""

    type: Literal["text"] = "text"
    text: str


class ImageUrl(BaseModel):
    url: str
    # "auto" | "low" | "high" — OpenAI vision detail hint.
    detail: Optional[Literal["auto", "low", "high"]] = None


class ImagePart(BaseModel):
    """An image segment in a multimodal message.

    `image_url.url` may be either a real URL or a data: URI
    (e.g. "data:image/png;base64,...").
    """

    type: Literal["image_url"] = "image_url"
    image_url: ImageUrl


class InputAudio(BaseModel):
    """Base64 audio payload for an audio content part.

    Unlike images, audio is not wrapped in a data: URI — the raw base64 goes
    in `data` and the container format is a separate field. OpenAI currently
    accepts only "wav" and "mp3".
    """

    data: str
    format: Literal["wav", "mp3"]


class AudioPart(BaseModel):
    """An audio segment in a multimodal message (user messages only)."""

    type: Literal["input_audio"] = "input_audio"
    input_audio: InputAudio


class FileData(BaseModel):
    """The payload of a `file` content part.

    Supply *either* an inline document (`file_data` base64 + `filename`) *or* a
    reference to a previously uploaded file (`file_id`). This is OpenAI's path
    for PDFs and other documents — distinct from `image_url`. All fields are
    optional so `exclude_none=True` drops whichever branch is unused.
    """

    file_data: Optional[str] = None
    filename: Optional[str] = None
    file_id: Optional[str] = None


class FilePart(BaseModel):
    """A document segment in a multimodal message (user messages only)."""

    type: Literal["file"] = "file"
    file: FileData


ContentPart = Union[TextPart, ImagePart, AudioPart, FilePart]


class ToolCall(BaseModel):
    """A tool invocation emitted by the model."""

    id: str
    name: str
    arguments: Dict[str, Any]


class Message(BaseModel):
    """A single chat message.

    `content` accepts either a plain string or a list of content parts
    (text + images) for multimodal user messages. Assistant messages that
    only contain tool calls have content=None.
    """

    model_config = ConfigDict(extra="forbid")

    role: Role
    content: Union[str, List[ContentPart], None] = None
    # The model's reasoning/thinking trace. Persisted and shown (web/CLI
    # history), but stripped in _message_to_openai — never replayed to the
    # model. See reasoning-support.md.
    reasoning: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None


# Default JSON Schema for a tool that takes no arguments. OpenAI expects a
# valid schema object rather than an empty dict.
_EMPTY_SCHEMA: Dict[str, Any] = {"type": "object", "properties": {}}


class LLMTool(BaseModel):
    """A tool the model may call, in neutral wire-format.

    This is the serialized *description* of a tool — name, human-readable
    description, and JSON Schema for arguments — that the LLM facade ships to
    the model. It is distinct from `tools.BaseTool`, which is the executable
    interface tool authors implement. See
    [.claude/specifications/tool-system.md](../.claude/specifications/tool-system.md).
    """

    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=lambda: dict(_EMPTY_SCHEMA))

    @classmethod
    def from_model(
        cls,
        args_model: Type[BaseModel],
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> "LLMTool":
        """Build a Tool from a Pydantic model describing its arguments.

        Defers all JSON Schema generation to the OpenAI SDK's public
        `pydantic_function_tool` helper, which emits a strict schema
        (additionalProperties=false, every field in `required`) compatible
        with function-calling.

        The helper returns OpenAI's `{"type":"function","function":{...}}`
        envelope; we unwrap it back into our neutral `Tool` shape so the
        provider-specific envelope only exists at request time in
        `LLM._build_tools`.

        `name` defaults to the model's class name. `description` defaults to
        the model's docstring (which the SDK also reads).
        """
        envelope = pydantic_function_tool(
            args_model,
            name=name or args_model.__name__,
            description=description,
        )
        fn = envelope["function"]
        params = dict(fn.get("parameters") or _EMPTY_SCHEMA)
        # The SDK stashes the docstring inside parameters.description as well;
        # drop it so `parameters` is a clean JSON Schema and the description
        # lives only on the Tool.
        params.pop("description", None)
        return cls(
            name=fn["name"],
            description=fn.get("description") or "",
            parameters=params,
        )


class Usage(BaseModel):
    """Token usage reported by the model."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    # Reasoning models bill thinking tokens here (from the SDK's
    # completion_tokens_details). None when the provider doesn't report it.
    reasoning_tokens: Optional[int] = None


class GenerateResponse(BaseModel):
    """Response returned from a non-streaming generate() call."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str
    # Neutral reasoning trace, read off the provider's configured response
    # field. None when reasoning is unconfigured or the provider didn't emit it.
    reasoning: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: Optional[str] = None
    usage: Optional[Usage] = None
    # The untouched SDK response — escape hatch for fields we haven't surfaced.
    raw: Any = None


class StructuredResponse(BaseModel, Generic[T]):
    """Response from generate_structured() — carries the parsed Pydantic instance.

    `parsed` is None only when the model refused to answer (in which case
    `refusal` holds the refusal string). Callers should check `refusal` before
    using `parsed`.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str
    reasoning: Optional[str] = None
    parsed: Optional[T] = None
    refusal: Optional[str] = None
    finish_reason: Optional[str] = None
    usage: Optional[Usage] = None
    raw: Any = Field(default=None, exclude=True)


class ToolCallDelta(BaseModel):
    """A partial tool call from a streaming response.

    OpenAI streams tool calls as fragments keyed by `index`: the first fragment
    for an index usually carries `id` and `function.name`, and subsequent
    fragments carry `arguments` as incremental JSON string chunks that must be
    concatenated. See the accumulator in `llm.llm` for the reassembly logic.
    """

    index: int
    id: Optional[str] = None
    name: Optional[str] = None
    arguments: Optional[str] = None


class StreamChunk(BaseModel):
    """One delta from a streaming generate() call."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str = ""
    # Neutral reasoning trace DELTA — a fragment, concatenated by the
    # StreamAccumulator exactly like `text`.
    reasoning: str = ""
    tool_calls: Optional[List[ToolCallDelta]] = None
    finish_reason: Optional[str] = None
    # Only present on the final chunk when the caller requests it via
    # stream_options={"include_usage": True} (the facade sets this by default).
    usage: Optional[Usage] = None
    raw: Any = None
