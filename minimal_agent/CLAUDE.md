# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dependency management uses `uv` (see [uv.lock](uv.lock) and [pyproject.toml](pyproject.toml)). Python >= 3.10.

- Install deps: `uv sync`
- Run the demo entrypoint: `uv run python main.py`
- Add a dependency: `uv add <pkg>`
- Format: `make format` (runs `uv run ruff format .`)
- Lint: `make lint` (runs `uv run ruff check .`)
- Auto-fix lint: `make lint-fix` (runs `uv run ruff check --fix .`)
- Run tests: `make test` (runs `uv run pytest`)

Ruff is the only linter/formatter. Its config lives in [pyproject.toml](pyproject.toml) under `[tool.ruff.lint]` and `[tool.ruff.format]` — enabled rule groups are `E`, `F`, `B`, `I`, `W` (with `B008` ignored).

## Testing

- Tests live in `tests/`, mirroring the source layout. pytest-asyncio is in auto mode, so `async def test_*` works without decorators.
- Run `make test` as the final step after any change that could affect behavior — new code, refactors, dependency bumps, config changes — and fix failures before handing back.
- **Skip `make test` for trivial edits** that cannot plausibly break tests: renaming a local variable, fixing a typo in a comment or docstring, editing a markdown file, touching `CLAUDE.md`, or adjusting whitespace. If in doubt, run them.

Configuration is loaded via `pydantic-settings` from environment variables and a `.env` file in the working directory. Copy [.env.example](.env.example) to `.env` and fill in `OPENAI_API_KEY` (and optionally `OPENAI_BASE_URL` to point at a local OpenAI-compatible server like vLLM / llama.cpp / LM Studio / Ollama's `/v1`).

## Style

- Prefer type-safe constructs over magic strings. Use `StrEnum`, `Literal`, or similar typed constants for fixed sets of values (e.g. `Backend.OPENAI` instead of `"openai"`). This catches typos at the type-checker level and enables autocompletion.

## Architecture

This is a minimal async LLM facade over the OpenAI Python SDK, designed so that the rest of the codebase never imports `openai` directly. The neutral types in [llm/types.py](llm/types.py) are the public surface; [llm/llm.py](llm/llm.py) is the only place that translates to/from OpenAI's SDK shapes.

### The `LLM` facade ([llm/llm.py](llm/llm.py))

One class wrapping `AsyncOpenAI` with three public coroutines:

- `generate(...)` — non-streaming chat completion, returns `GenerateResponse`.
- `generate_structured(..., schema=MyModel)` — uses the SDK's `chat.completions.parse` to get a validated Pydantic instance back. **Backend caveat:** requires a server that honors strict `json_schema` response_format. OpenAI and vLLM work; llama.cpp works via grammars; Ollama's `/v1` does *not* reliably honor it; **Anthropic's OpenAI-compat layer silently ignores `response_format`** (and OpenRouter inherits this when routing to Anthropic models) — prompt-engineer JSON manually or use the native provider SDK for those targets.
- `stream(...)` — async iterator of `StreamChunk`. Sets `stream_options.include_usage=True` by default so the final (choice-less) event carries usage; the facade surfaces that as a final `StreamChunk` with `usage` set rather than dropping it.

The `.raw` property exposes the underlying `AsyncOpenAI` client as an escape hatch for features the facade hasn't surfaced.

**Backends.** `LLM(..., backend=...)` accepts a `Backend` enum value (`Backend.OPENAI` (default), `Backend.OPENROUTER`, `Backend.ANTHROPIC`, or `Backend.LOCALHOST`). The latter two set a default `base_url` for each provider's OpenAI-compatible endpoint ([OpenRouter quickstart](https://openrouter.ai/docs/quickstart), [Anthropic OpenAI SDK compat](https://platform.claude.com/docs/en/api/openai-sdk)); an explicit `base_url` in `client_kwargs` still wins. OpenRouter's optional `site_url` / `app_name` kwargs become `HTTP-Referer` / `X-Title` headers for their leaderboards. Beyond `response_format`, Anthropic's compat layer also silently ignores `seed`, `frequency_penalty`, `presence_penalty`, `logprobs`, and `user` — `_completion_params` still sends them, they just have no effect.

Request building is centralized in `_completion_params`: every optional parameter is only inserted when non-None, so provider defaults (and the SDK's own defaults) are preserved. Note that `max_tokens` is mapped to `max_completion_tokens` because the old field is deprecated and reasoning models reject it.

### Neutral types ([llm/types.py](llm/types.py))

Pydantic models mirroring (but not depending on) the OpenAI chat shapes:

- `Message` — `content` can be `str`, a list of `ContentPart` (`TextPart` / `ImagePart` for multimodal), or `None` (assistant messages that are pure tool calls). Tool-result messages set `role="tool"` + `tool_call_id`.
- `ToolCall` stores `arguments` as a **parsed dict** for ergonomics; the facade `json.dumps` on the way out to OpenAI and `json.loads` on the way in. If the model emits malformed JSON, the parser falls back to `{"__raw__": <string>}` rather than raising.
- `LLMTool` is the provider-neutral wire-format description (`name` / `description` / `parameters` JSON Schema) that the facade ships to the model. It is distinct from `tools.BaseTool`, which is the executable tool interface authors implement — see [.claude/specifications/tool-system.md](.claude/specifications/tool-system.md). `LLMTool.from_model(PydanticModel)` delegates to the SDK's `pydantic_function_tool` helper to generate a strict schema (`additionalProperties=false`, all fields required), then unwraps the OpenAI envelope back into the neutral shape. OpenAI's function-calling envelope only exists at request time inside `_build_tools`.
- `ToolChoice` accepts `"auto" | "none" | "required"` *or* a bare tool name string (which the facade wraps into OpenAI's forced-call object).

### Tool-call streaming

OpenAI streams tool calls as fragments keyed by `index`: the first fragment usually carries `id` and `function.name`, subsequent fragments carry `arguments` as incremental JSON string chunks that must be concatenated. `accumulate_tool_calls(chunks)` in [llm/llm.py](llm/llm.py) does the reassembly for callers that want "streaming text + completed tool calls" without writing the bookkeeping themselves.

### Config ([config.py](config.py))

`Settings` is a `BaseSettings` with all OpenAI client params (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_TIMEOUT`, `OPENAI_MAX_RETRIES`) as `Optional`. Callers must **filter out `None` values** before forwarding to `LLM(...)` because the SDK rejects `None` for `max_retries` / `timeout` and has its own defaults worth preserving — see the `overrides` dict in [main.py](main.py) for the pattern.
