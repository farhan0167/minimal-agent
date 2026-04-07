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

A minimal async agent framework: an **agent loop** drives an LLM that can call tools, with the LLM details abstracted behind a provider-agnostic facade. The three pillars are the agent loop, the tool system, and the LLM facade.

### Agent loop ([agent/](agent/))

`Agent` ([agent/agent.py](agent/agent.py)) owns the decide-act-observe loop. `Agent.run()` is an iterative async generator: call `LLM.generate` with the current context and tools → yield the assistant message → if it contains tool calls, dispatch each via `tools/dispatcher.py`, yield the tool-result messages → repeat. Stops when the model produces no tool calls or `max_turns` (default 10) is exhausted. The agent is stateless per-run; conversation state lives in `Context`.

**Context & storage.** `Context` ([agent/context.py](agent/context.py)) is the agent's interface to conversation state. It composes a `MessageStore` ([agent/message_store.py](agent/message_store.py)) with a system prompt and a projection strategy (default: return all messages). `MessageStore` is append-only; when constructed with a path, each append writes a JSONL line to disk.

**Sessions.** `Session` ([agent/session.py](agent/session.py)) is the user-facing unit of conversation. It owns a `Context` and a `SessionMeta` dataclass (identity, model, backend, timestamps, usage). Factory methods `Session.create()` and `Session.load()` handle disk persistence (JSONL messages + JSON metadata). `Session.load()` validates that model/backend match the original session.

### Tool system ([tools/](tools/))

Three layers:

1. **Definition** — `BaseTool[InputT, OutputT]` ([tools/base.py](tools/base.py)) is the abstract class tool authors implement. Requires `name`, `input_schema` (a Pydantic model), and `invoke()`. Optional hooks: `validate()`, `needs_permission()`, `render_result_for_assistant()`. `as_llm_tool()` projects the Pydantic schema into an `LLMTool` for the wire format.
2. **Dispatch** — `dispatch()` ([tools/dispatcher.py](tools/dispatcher.py)) runs the full pipeline: lookup → parse/validate args → semantic validation → permission check → invoke → serialize result. All errors are caught and returned as tool-result messages so the agent loop never crashes.
3. **Context** — `ToolContext` ([tools/context.py](tools/context.py)) is a per-call bag passed to every tool invocation (currently a placeholder for future fields like cancellation tokens, loggers, permission callbacks).

Concrete tools live under [tools/builtin/](tools/builtin/) (e.g. `get_weather`). See [.claude/specifications/tool-system.md](.claude/specifications/tool-system.md) for the full tool-authoring contract.

### LLM facade ([llm/](llm/))

The rest of the codebase never imports `openai` directly. [llm/llm.py](llm/llm.py) wraps `AsyncOpenAI` with three public coroutines (`generate`, `generate_structured`, `stream`) and translates between the neutral Pydantic types in [llm/types.py](llm/types.py) and OpenAI's SDK shapes.

**Backends.** `Backend` enum selects provider: `OPENAI` (default), `OPENROUTER`, `ANTHROPIC`, `LOCALHOST`. Each sets an appropriate `base_url`; an explicit `base_url` still wins. Anthropic's OpenAI-compat layer silently ignores `response_format`, `seed`, and several other params — see docstrings for details.

**Key types** in [llm/types.py](llm/types.py): `Message` (supports multimodal content and tool-result role), `ToolCall` (arguments stored as parsed dict), `LLMTool` (provider-neutral tool schema), `GenerateResponse`, `StreamChunk`.

### Config ([config.py](config.py))

`Settings` (pydantic-settings) reads from env vars / `.env`. Env vars are prefixed `LLM_BACKEND_*` for backend/API key/base URL, plus `LLM_MODEL` (default `gpt-4o-mini`) and `SESSIONS_DIR` (default `.minimal_agent/sessions`). Filter out `None` values before forwarding to `LLM()` — the SDK has its own defaults worth preserving.
