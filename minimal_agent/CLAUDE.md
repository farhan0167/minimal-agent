# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dependency management uses `uv` (see [uv.lock](uv.lock) and [pyproject.toml](pyproject.toml)). Python >= 3.10.

- Install deps: `uv sync`
- Run the CLI: `python ../cli_main.py` (from repo root, with `minimal_agent` installed)
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

The installable package lives under `src/minimal_agent/` (src layout). The CLI (`cli/`, `main.py`) is a standalone consumer at the project root — not part of the installed package.

### Agent loop ([src/minimal_agent/agent/](src/minimal_agent/agent/))

`Agent` ([src/minimal_agent/agent/agent.py](src/minimal_agent/agent/agent.py)) owns the agent's identity and the decide-act-observe loop. Identity is defined by the behavior prompt (`prompt`), context sources (`context_sources`, partitioned by placement at construction), and tools. `Agent.run()` is an iterative async generator: signal `context.begin_run()` once, then per iteration call the LLM with `await context.assemble()` and the tool schemas → yield the assistant message → if it contains tool calls, dispatch each via `src/minimal_agent/tools/dispatcher.py`, yield the tool-result messages → repeat. Stops when the model produces no tool calls or `max_turns` (default 10, counts LLM calls per run) is exhausted. The agent is stateless per-run; conversation state lives in `Context`, and the loop never edits the message list itself.

Sessions are created through the agent's factories — `agent.create_session()` / `agent.load_session()` — which build the system prompt, forward model/backend from the agent's LLM, and attach the agent's live (RUN/CALL-placed) context sources to the session's `Context`. Default prompt (no `prompt` arg) uses the built-in software engineering agent and auto-includes `GitStatusSource` + `DirectoryTreeSource`. Custom prompts get no context sources by default (blank slate). See [.claude/specifications/agent-session-factories.md](.claude/specifications/agent-session-factories.md).

**Context sources & placement.** [src/minimal_agent/context_sources/](src/minimal_agent/context_sources/) (a top-level package used by both `agent/` and `system_prompt/`) defines the `ContextSource` protocol (structural typing, no inheritance required), the `Placement` enum, and the built-in sources. `base.py` holds the protocol/enum/resolver helpers; each built-in source lives in its own module (`agents_md.py`, `git_status.py`, `directory_tree.py`, `skills.py`) and the package `__init__.py` re-exports them all, so callers import from `minimal_agent.context_sources` regardless of layout. A source's class-level `placement` declares when it's gathered and where its output lands: `SESSION` (once at session creation, baked into the system prompt — the default; `DirectoryTreeSource`, `SkillsContextSource`), `RUN` (once per `Agent.run()`, merged into the run's user message — `GitStatusSource`), or `CALL` (before every LLM call, standalone tail carrier — no built-in uses it). Injected content is never persisted to the transcript. See [.claude/specifications/fresh-context-sources.md](.claude/specifications/fresh-context-sources.md).

**Context & storage.** `Context` ([src/minimal_agent/agent/context.py](src/minimal_agent/agent/context.py)) is the agent's interface to conversation state. It composes a `MessageStore` ([src/minimal_agent/agent/message_store.py](src/minimal_agent/agent/message_store.py)) with a system prompt and a projection strategy (default: return all messages). It is also the single assembly point for what the LLM sees: the loop calls `context.begin_run()` once per run and `await context.assemble()` before each LLM call; `assemble()` returns `get_messages()` plus live-source blocks per the merge rule. `get_messages()` stays sync and pure (no I/O, no injected blocks) — safe for UIs and tests. `MessageStore` is append-only; when constructed with a path, each append writes a JSONL line to disk.

**Sessions.** `Session` ([src/minimal_agent/agent/session.py](src/minimal_agent/agent/session.py)) is the user-facing root of a conversation: a `SessionMeta` dataclass (identity, model, backend, timestamps, usage, workspace root), the root scope's `Context`, and automatic usage rollup (it subscribes to the root scope's totals — hosts never call an accounting method). Persistence policy lives in `SessionManager` (same file): base dir, sink wiring, `create_session()` / `load_session()` / `read_meta()` / `list_sessions()`. `load_session()` validates that model/backend match the original session. The Agent holds a manager (`Agent(..., sessions=...)`, default records under `.minimal_agent/sessions`) and its factories delegate to it — prefer those, they keep prompt, settings, and live sources consistent by construction.

**Scopes & observability.** `Scope` ([src/minimal_agent/agent/scope.py](src/minimal_agent/agent/scope.py)) is a node in the session's recording tree: an `EventEmitter` + `MessageStore` + `child()` for spawning nested recorded agents. The session root is a `RecordedScope` (sinks: `TraceSink` → `events.jsonl`, `CallLogSink` → `calls.jsonl` + shared session-root `blobs/`, `ScopeMetaSink` → usage/fingerprint); a bare `Context()` gets a `NullScope` (zero-sink emitter, in-memory store) so there are no `None` checks anywhere. A tool that runs its own agent opens `with ctx.scope.child(spawned_by=..., task=..., tool_call_id=ctx.tool_call_id) as scope:` — this allocates `agents/a-<id>/` under the session with the identical artifact kit, emits `agent.spawn`/`agent.end` on the parent's trace (truthful status even on crash/cancel, via the CM exit), writes `agent.json` parentage, and forwards the child's usage to the session totals. `spawn_agents` is the reference implementation. Concurrency safety across sibling scopes is isolation (per-scope emitters and files), not locking. Events live in [src/minimal_agent/events.py](src/minimal_agent/events.py); emission is fire-and-forget and can never break a run.

### System prompt ([src/minimal_agent/system_prompt/](src/minimal_agent/system_prompt/))

Builds the agent's system prompt from three parts: a **behavior prompt** (static markdown), an **environment block** (dynamic `<env>` XML with workspace root, platform, date, git status), and **context blocks** (dynamic `<context>` XML from opt-in sources). See [.claude/specifications/system-prompt-module.md](.claude/specifications/system-prompt-module.md) for the full design spec.

- **[builder.py](src/minimal_agent/system_prompt/builder.py)** — `build_system_prompt()` assembles all parts into a single string; it gathers only `SESSION`-placed sources (the prompt is a snapshot, and its context preamble says so). `load_prompt()` resolves `str | Path | None` to a prompt string. `build_context_blocks()` formats tagged blocks and is reused by `Context.assemble()` (with `preamble=None`) for live injection.
- **[env.py](src/minimal_agent/system_prompt/env.py)** — `build_env_block()` produces the `<env>` block.
- **[defaults/behavior.md](src/minimal_agent/system_prompt/defaults/behavior.md)** — The default behavior prompt (software engineering agent).

Context sources live at the package top level ([src/minimal_agent/context_sources/](src/minimal_agent/context_sources/)); `system_prompt/__init__.py` re-exports them for backward compatibility. The module has no imports from `agent/`, `tools/`, or `llm/` — it's a pure utility that takes configuration and produces a string.

### Tool system ([src/minimal_agent/tools/](src/minimal_agent/tools/))

Three layers:

1. **Definition** — `BaseTool[InputT, OutputT]` ([src/minimal_agent/tools/base.py](src/minimal_agent/tools/base.py)) is the abstract class tool authors implement. Requires `name`, `input_schema` (a Pydantic model), and `invoke()`. Optional hooks: `validate()`, `needs_permission()`, `render_result_for_assistant()`. `as_llm_tool()` projects the Pydantic schema into an `LLMTool` for the wire format.
2. **Dispatch** — `dispatch()` ([src/minimal_agent/tools/dispatcher.py](src/minimal_agent/tools/dispatcher.py)) runs the full pipeline: lookup → parse/validate args → semantic validation → permission check → invoke → serialize result. All errors are caught and returned as tool-result messages so the agent loop never crashes.
3. **Context** — `ToolContext` ([src/minimal_agent/tools/context.py](src/minimal_agent/tools/context.py)) is a per-call bag passed to every tool invocation. Carries `permission_callback` (interactive confirmation), `scope` (the recording node — defaults to a `NullScope`; tools that embed agents spawn children from it), and `tool_call_id` (stamped per call by the dispatcher). New fields (cancellation tokens, loggers) land here as concrete tools need them.

Concrete tools live under [src/minimal_agent/tools/builtin/](src/minimal_agent/tools/builtin/) (e.g. `get_weather`). See [.claude/specifications/tool-system.md](.claude/specifications/tool-system.md) for the full tool-authoring contract.

### LLM facade ([src/minimal_agent/llm/](src/minimal_agent/llm/))

The rest of the codebase never imports `openai` directly. [src/minimal_agent/llm/llm.py](src/minimal_agent/llm/llm.py) wraps `AsyncOpenAI` with three public coroutines (`generate`, `generate_structured`, `stream`) and translates between the neutral Pydantic types in [src/minimal_agent/llm/types.py](src/minimal_agent/llm/types.py) and OpenAI's SDK shapes.

**Backends.** `Backend` enum selects provider: `OPENAI` (default), `OPENROUTER`, `ANTHROPIC`, `LOCALHOST`. Each sets an appropriate `base_url`; an explicit `base_url` still wins. Anthropic's OpenAI-compat layer silently ignores `response_format`, `seed`, and several other params — see docstrings for details.

**Key types** in [src/minimal_agent/llm/types.py](src/minimal_agent/llm/types.py): `Message` (supports multimodal content and tool-result role), `ToolCall` (arguments stored as parsed dict), `LLMTool` (provider-neutral tool schema), `GenerateResponse`, `StreamChunk`.

### Config ([src/minimal_agent/config.py](src/minimal_agent/config.py))

`Settings` (pydantic-settings) reads from env vars / `.env`. Env vars are prefixed `LLM_BACKEND_*` for backend/API key/base URL, plus `LLM_MODEL` (default `gpt-4o-mini`) and `SESSIONS_DIR` (default `.minimal_agent/sessions`). Filter out `None` values before forwarding to `LLM()` — the SDK has its own defaults worth preserving.

### CLI ([../cli/](../cli/), [../cli_main.py](../cli_main.py))

The CLI is a standalone consumer of the `minimal_agent` package — not part of the installed library. It lives at the repo root as a sibling project alongside `streamlit_client/`. Depends on `rich` and `prompt-toolkit` (dev dependencies). Run via `python ../cli_main.py` from the repo root.

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
| `on_usage` | `(Usage) -> None` | Called after each LLM API call with token counts. Display-only (live counters) — session accounting is automatic via the scope's usage sink |
| `permission_callback` | `async (str, str) -> bool` | Called when a tool needs user confirmation. Receives `(tool_name, description)`, returns `True` to allow |

### Adding a new callback

**1. Define the type in `src/minimal_agent/tools/context.py`:**

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
