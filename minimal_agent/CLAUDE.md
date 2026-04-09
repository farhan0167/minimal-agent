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

A minimal async agent framework: an **agent loop** drives an LLM that can call tools, with the LLM details abstracted behind a provider-agnostic facade. The four pillars are the agent loop, the system prompt module, the tool system, and the LLM facade.

### Agent loop ([agent/](agent/))

`Agent` ([agent/agent.py](agent/agent.py)) owns the agent's identity and the decide-act-observe loop. Identity is defined by the behavior prompt (`prompt`), context sources (`context_sources`), and tools. `Agent.run()` is an iterative async generator: call `LLM.generate` with the current context and tools → yield the assistant message → if it contains tool calls, dispatch each via `tools/dispatcher.py`, yield the tool-result messages → repeat. Stops when the model produces no tool calls or `max_turns` (default 10) is exhausted. The agent is stateless per-run; conversation state lives in `Context`.

The Agent constructs the system prompt via `agent.build_system_prompt(workspace_root)`, which the caller passes to `Session.create()`. Default prompt (no `prompt` arg) uses the built-in software engineering agent and auto-includes `GitStatusSource` + `DirectoryTreeSource`. Custom prompts get no context sources by default (blank slate).

**Context & storage.** `Context` ([agent/context.py](agent/context.py)) is the agent's interface to conversation state. It composes a `MessageStore` ([agent/message_store.py](agent/message_store.py)) with a system prompt and a projection strategy (default: return all messages). `MessageStore` is append-only; when constructed with a path, each append writes a JSONL line to disk.

**Sessions.** `Session` ([agent/session.py](agent/session.py)) is the user-facing unit of conversation. It owns a `Context` and a `SessionMeta` dataclass (identity, model, backend, timestamps, usage). Factory methods `Session.create()` and `Session.load()` handle disk persistence (JSONL messages + JSON metadata). `Session.load()` validates that model/backend match the original session.

### System prompt ([system_prompt/](system_prompt/))

Builds the agent's system prompt from three parts: a **behavior prompt** (static markdown), an **environment block** (dynamic `<env>` XML with workspace root, platform, date, git status), and **context blocks** (dynamic `<context>` XML from opt-in sources). See [.claude/specifications/system-prompt-module.md](.claude/specifications/system-prompt-module.md) for the full design spec.

- **[builder.py](system_prompt/builder.py)** — `build_system_prompt()` assembles all parts into a single string. `load_prompt()` resolves `str | Path | None` to a prompt string.
- **[env.py](system_prompt/env.py)** — `build_env_block()` produces the `<env>` block.
- **[context_sources.py](system_prompt/context_sources.py)** — `ContextSource` protocol (structural typing, no inheritance required) plus built-in sources: `GitStatusSource`, `DirectoryTreeSource`. Context sources are gathered concurrently once per session, not per turn.
- **[defaults/behavior.md](system_prompt/defaults/behavior.md)** — The default behavior prompt (software engineering agent).

The module has no imports from `agent/`, `tools/`, or `llm/` — it's a pure utility that takes configuration and produces a string.

### Tool system ([tools/](tools/))

Three layers:

1. **Definition** — `BaseTool[InputT, OutputT]` ([tools/base.py](tools/base.py)) is the abstract class tool authors implement. Requires `name`, `input_schema` (a Pydantic model), and `invoke()`. Optional hooks: `validate()`, `needs_permission()`, `render_result_for_assistant()`. `as_llm_tool()` projects the Pydantic schema into an `LLMTool` for the wire format.
2. **Dispatch** — `dispatch()` ([tools/dispatcher.py](tools/dispatcher.py)) runs the full pipeline: lookup → parse/validate args → semantic validation → permission check → invoke → serialize result. All errors are caught and returned as tool-result messages so the agent loop never crashes.
3. **Context** — `ToolContext` ([tools/context.py](tools/context.py)) is a per-call bag passed to every tool invocation. Currently carries `permission_callback` for interactive user confirmation. New fields (cancellation tokens, loggers) land here as concrete tools need them.

Concrete tools live under [tools/builtin/](tools/builtin/) (e.g. `get_weather`). See [.claude/specifications/tool-system.md](.claude/specifications/tool-system.md) for the full tool-authoring contract.

### LLM facade ([llm/](llm/))

The rest of the codebase never imports `openai` directly. [llm/llm.py](llm/llm.py) wraps `AsyncOpenAI` with three public coroutines (`generate`, `generate_structured`, `stream`) and translates between the neutral Pydantic types in [llm/types.py](llm/types.py) and OpenAI's SDK shapes.

**Backends.** `Backend` enum selects provider: `OPENAI` (default), `OPENROUTER`, `ANTHROPIC`, `LOCALHOST`. Each sets an appropriate `base_url`; an explicit `base_url` still wins. Anthropic's OpenAI-compat layer silently ignores `response_format`, `seed`, and several other params — see docstrings for details.

**Key types** in [llm/types.py](llm/types.py): `Message` (supports multimodal content and tool-result role), `ToolCall` (arguments stored as parsed dict), `LLMTool` (provider-neutral tool schema), `GenerateResponse`, `StreamChunk`.

### Config ([config.py](config.py))

`Settings` (pydantic-settings) reads from env vars / `.env`. Env vars are prefixed `LLM_BACKEND_*` for backend/API key/base URL, plus `LLM_MODEL` (default `gpt-4o-mini`) and `SESSIONS_DIR` (default `.minimal_agent/sessions`). Filter out `None` values before forwarding to `LLM()` — the SDK has its own defaults worth preserving.

## Adding Callbacks to the Agent Loop

The agent loop supports callbacks — functions passed into `agent.run()` that get invoked at specific points during execution. This is how the framework hooks into the host environment (CLI, web server, tests) without the core loop knowing about UI or I/O.

### How it works

`Agent.run()` accepts optional callback parameters. These flow into `ToolContext`, which is created fresh each turn and passed to every tool invocation via the dispatcher.

```
agent.run(context, permission_callback=my_fn)
    → ToolContext(permission_callback=my_fn)       # created per turn
        → dispatcher checks needs_permission()
            → calls my_fn(tool_name, description)  # your code runs here
```

### Existing callbacks

| Callback | Signature | Purpose |
|---|---|---|
| `on_usage` | `(Usage) -> None` | Called after each LLM API call with token counts |
| `permission_callback` | `async (str, str) -> bool` | Called when a tool needs user confirmation. Receives `(tool_name, description)`, returns `True` to allow |

### Adding a new callback

**1. Define the type in `tools/context.py`:**

```python
NewCallback = Callable[[SomeInput], Awaitable[SomeOutput]]
```

**2. Add the field to `ToolContext`:**

```python
@dataclass
class ToolContext:
    permission_callback: Optional[PermissionCallback] = field(default=None)
    new_callback: Optional[NewCallback] = field(default=None)  # add here
```

**3. Accept it in `Agent.run()` and pass it into `ToolContext`:**

```python
async def run(
    self,
    context: Context,
    *,
    on_usage: Optional[OnUsageCallback] = None,
    permission_callback: Optional[PermissionCallback] = None,
    new_callback: Optional[NewCallback] = None,  # add here
) -> AsyncGenerator[Message, None]:
    for _turn in range(self._max_turns):
        ctx = ToolContext(
            permission_callback=permission_callback,
            new_callback=new_callback,  # pass through
        )
        ...
```

**4. Use it where needed** (dispatcher, a specific tool, etc.):

```python
if ctx.new_callback is not None:
    result = await ctx.new_callback(some_input)
```

**5. Provide the implementation in the host** (CLI, tests, etc.):

```python
# In the REPL
async for msg in agent.run(
    session.context,
    new_callback=my_implementation,
)
```

### Design rules

- **Callbacks are always optional.** If no callback is set, the behavior should degrade gracefully (skip the check, use a default, etc.). This keeps tests simple and makes the agent usable in non-interactive contexts.
- **Callbacks are async.** Even if your implementation is synchronous, wrap it in an `async def`. This keeps the interface uniform and avoids blocking the event loop.
- **`ToolContext` is the carrier.** Don't pass callbacks directly to tools or the dispatcher — route them through `ToolContext` so every tool has access without changing signatures.
- **No field lands speculatively.** Only add a callback when a concrete tool or feature genuinely needs it.
