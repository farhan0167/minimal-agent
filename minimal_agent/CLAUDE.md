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

Ruff is the only linter/formatter. Its config lives in [pyproject.toml](pyproject.toml) under `[tool.ruff.lint]` and `[tool.ruff.format]` — enabled rule groups are `E`, `F`, `B`, `I`, `W` (with `B008` ignored). There is no test suite configured yet.

Configuration is loaded via `pydantic-settings` from environment variables and a `.env` file in the working directory. Copy [.env.example](.env.example) to `.env` and fill in `OPENAI_API_KEY` (and optionally `OPENAI_BASE_URL` to point at a local OpenAI-compatible server like vLLM / llama.cpp / LM Studio / Ollama's `/v1`).

## Architecture

This is a minimal async LLM facade over the OpenAI Python SDK, designed so that the rest of the codebase never imports `openai` directly. The neutral types in [llm/types.py](llm/types.py) are the public surface; [llm/llm.py](llm/llm.py) is the only place that translates to/from OpenAI's SDK shapes.

### The `LLM` facade ([llm/llm.py](llm/llm.py))

One class wrapping `AsyncOpenAI` with three public coroutines:

- `generate(...)` — non-streaming chat completion, returns `GenerateResponse`.
- `generate_structured(..., schema=MyModel)` — uses the SDK's `chat.completions.parse` to get a validated Pydantic instance back. **Backend caveat:** requires a server that honors strict `json_schema` response_format. OpenAI and vLLM work; llama.cpp works via grammars; Ollama's `/v1` does *not* reliably honor it — prompt-engineer JSON manually for Ollama targets.
- `stream(...)` — async iterator of `StreamChunk`. Sets `stream_options.include_usage=True` by default so the final (choice-less) event carries usage; the facade surfaces that as a final `StreamChunk` with `usage` set rather than dropping it.

The `.raw` property exposes the underlying `AsyncOpenAI` client as an escape hatch for features the facade hasn't surfaced.

Request building is centralized in `_completion_params`: every optional parameter is only inserted when non-None, so provider defaults (and the SDK's own defaults) are preserved. Note that `max_tokens` is mapped to `max_completion_tokens` because the old field is deprecated and reasoning models reject it.

### Neutral types ([llm/types.py](llm/types.py))

Pydantic models mirroring (but not depending on) the OpenAI chat shapes:

- `Message` — `content` can be `str`, a list of `ContentPart` (`TextPart` / `ImagePart` for multimodal), or `None` (assistant messages that are pure tool calls). Tool-result messages set `role="tool"` + `tool_call_id`.
- `ToolCall` stores `arguments` as a **parsed dict** for ergonomics; the facade `json.dumps` on the way out to OpenAI and `json.loads` on the way in. If the model emits malformed JSON, the parser falls back to `{"__raw__": <string>}` rather than raising.
- `Tool` is provider-neutral (`name` / `description` / `parameters` JSON Schema). `Tool.from_model(PydanticModel)` delegates to the SDK's `pydantic_function_tool` helper to generate a strict schema (`additionalProperties=false`, all fields required), then unwraps the OpenAI envelope back into the neutral shape. OpenAI's function-calling envelope only exists at request time inside `_build_tools`.
- `ToolChoice` accepts `"auto" | "none" | "required"` *or* a bare tool name string (which the facade wraps into OpenAI's forced-call object).

### Tool-call streaming

OpenAI streams tool calls as fragments keyed by `index`: the first fragment usually carries `id` and `function.name`, subsequent fragments carry `arguments` as incremental JSON string chunks that must be concatenated. `accumulate_tool_calls(chunks)` in [llm/llm.py](llm/llm.py) does the reassembly for callers that want "streaming text + completed tool calls" without writing the bookkeeping themselves.

### Config ([config.py](config.py))

`Settings` is a `BaseSettings` with all OpenAI client params (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_TIMEOUT`, `OPENAI_MAX_RETRIES`) as `Optional`. Callers must **filter out `None` values** before forwarding to `LLM(...)` because the SDK rejects `None` for `max_retries` / `timeout` and has its own defaults worth preserving — see the `overrides` dict in [main.py](main.py) for the pattern.
