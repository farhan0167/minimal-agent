# minimal_agent: User Guide

This is the full reference guide to building with `minimal_agent`. For installation, backend setup, and a five-minute quickstart, see the [root README](../README.md) first — this file picks up from there and covers everything the library can do.

Built on top of the OpenAI SDK (works with any OpenAI-compatible API), Pydantic for schemas, and `asyncio` for concurrency.

## Configuring providers

The LLM facade talks to any OpenAI-compatible provider through one `Backend` enum. You pick the backend and model on the `LLM`, and supply credentials through environment variables (a `.env` file in the working directory works too — see [.env.example](.env.example)).

```python
from minimal_agent.llm import LLM
from minimal_agent.config import Backend

llm = LLM(model="gpt-4o-mini", backend=Backend.OPENAI)
```

### Environment variables

Config is loaded once into `settings` ([config.py](src/minimal_agent/config.py)) via `pydantic-settings`, reading process env vars first, then `.env`. The `LLM` reads these as defaults when the corresponding constructor argument isn't passed.

| Variable | Purpose |
|---|---|
| `LLM_BACKEND` | Which provider: `openai` (default), `openrouter`, `anthropic`, or `localhost` |
| `LLM_BACKEND_API_KEY` | API key for the active backend |
| `LLM_BACKEND_BASE_URL` | Override the provider's base URL. **Required** for `localhost` |
| `LLM_MODEL` | Default model name (default `gpt-4o-mini`) |
| `LLM_BACKEND_SITE_URL` / `LLM_BACKEND_APP_NAME` | OpenRouter leaderboard attribution — ignored by other backends |
| `OPENAI_TIMEOUT` / `OPENAI_MAX_RETRIES` | Per-request timeout (seconds) and SDK retry count |

Each backend sets a sensible default base URL — OpenRouter and Anthropic point at their OpenAI-compatible endpoints, OpenAI uses the SDK default. An explicit `LLM_BACKEND_BASE_URL` (or `base_url=` on `LLM`) always wins.

**API key resolution.** Set `LLM_BACKEND_API_KEY` and it's used for whatever backend is active. If it's unset, the active backend falls back to its conventional key — `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, or `ANTHROPIC_API_KEY` — so existing `.env` files keep working. The `localhost` backend needs no key (it sends `not-needed`).

### Per backend

| Backend | Key | `LLM_MODEL` examples | Notes |
|---|---|---|---|
| `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` | Default backend |
| `openrouter` | `OPENROUTER_API_KEY` | `anthropic/claude-opus-4-5`, `openai/gpt-4o-mini` | Any model on OpenRouter |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-opus-4-6`, `claude-sonnet-4-6` | Anthropic's OpenAI-compat layer silently ignores `response_format`, `seed`, and some other params |
| `localhost` | none | whatever your server expects | For vLLM, llama.cpp, LM Studio, Ollama — you **must** set `LLM_BACKEND_BASE_URL` (e.g. `http://localhost:8000/v1`) |

A minimal `.env` for, say, OpenRouter:

```bash
LLM_BACKEND=openrouter
LLM_BACKEND_API_KEY=sk-or-...
LLM_MODEL=anthropic/claude-opus-4-5
```

Constructor arguments override the environment — pass `api_key=`, `base_url=`, `timeout=`, or `max_retries=` to `LLM(...)` to bypass `settings` entirely, which is handy for wiring multiple providers in one process.

## Streaming responses

By default `agent.run()` yields one complete `Message` per step. Pass `stream=True` to also receive incremental `StreamChunk`s as tokens arrive — useful for live-printing the assistant's reply. Each assistant turn yields its chunks first, then the committed `Message` (the one added to the conversation); tool-result steps are always plain `Message`s. Switch on the type to tell a live delta from a committed message:

```python
from minimal_agent.llm import StreamChunk

async for item in agent.run(session.context, stream=True):
    if isinstance(item, StreamChunk):
        print(item.text, end="", flush=True)  # live token
    elif item.role == Role.ASSISTANT and item.content:
        print()  # assistant turn committed — finish the line
```

Token usage rides the final chunk of each turn, so `on_usage` works the same in both modes. (`on_usage` is a display hook for live counters — session accounting happens automatically, no wiring needed.)

### Resuming a session

Sessions are persisted to disk automatically. To pick up where you left off:

```python
session = await agent.load_session("20260408-143022-a1b2")  # id from a previous create_session()
```

The agent rebuilds the system prompt fresh against the session's persisted workspace (rebuild, don't restore — nothing stale is replayed) and raises `SessionConfigMismatchError` if the session was created with a different model, backend, or workspace.

## Concepts

![minimal-agent](../docs/images/minimal-agent-overview.png)

### Agent

The `Agent` is the core loop. It takes an LLM, a list of tools, and a prompt that defines its personality. Each call to `agent.run(context)` drives a decide-act-observe cycle: ask the LLM what to do → execute tool calls → feed results back → repeat until the LLM is done or `max_turns` is hit.

The agent owns its **identity** — the same agent instance can drive many sessions, and every session inherits its prompt and behavior.

### Session

A `Session` is a single conversation. It holds the message history and metadata (model, backend, timestamps, token usage, workspace root). Sessions are created with `agent.create_session()` and resumed with `agent.load_session()` — the factories stamp the agent's identity onto the session, so the prompt, settings, and context sources are always consistent.

Where sessions live — and how they're recorded — is a `SessionManager`. A default one records under `.minimal_agent/sessions/`; construct one only to change policy:

```python
from minimal_agent import SessionManager

agent = Agent(llm=llm, tools=[...], workspace_root=workspace,
              sessions=SessionManager(base_dir=Path("/srv/sessions")))
recent = agent.sessions.list_sessions()
```

Every session records itself as it runs: the transcript (`messages.jsonl`), a timeline of everything that happened (`events.jsonl`), and a byte-exact audit of every LLM call (`calls.jsonl` + `blobs/`). Token usage — including usage from any sub-agents — is accounted into `session.json` automatically.

### Scope

A `Scope` is one node in a session's recording tree. The session root is a scope; a tool that runs its own agent opens a *child scope* under it (`ctx.scope.child(...)`), which gets the identical artifact kit in `agents/<agent-id>/` inside the session directory — full transcript, timeline, and call audit for the nested agent, linked to the exact tool call that spawned it. You only touch scopes when writing a tool that embeds an agent; everything else records itself.

### Context

`Context` is the agent's view of the conversation. It wraps a `MessageStore` (append-only message log) with the system prompt and a projection strategy. Each LLM call goes through `context.assemble()`, which prepends the system prompt, projects the history, and injects fresh content from any RUN/CALL-placed context sources — without ever writing that content to the transcript. `get_messages()` returns the clean conversation (no injected blocks, no I/O), which is what UIs should render.

### Tools

Tools are how the agent interacts with the world. Each tool is a class that inherits from `BaseTool` and defines an input schema (Pydantic model) and an `invoke()` method. The framework handles argument parsing, validation, permission checks, and error handling — your tool just does its job.

**Built-in tools:**

| Tool | What it does |
|---|---|
| `ReadFile` | Read files with optional offset/limit |
| `WriteFile` | Create or overwrite files |
| `RunShell` | Execute shell commands with timeout and permission checks |
| `Grep` | Search file contents using ripgrep |
| `Glob` | Find files by name pattern |

### Spawning sub-agents

The built-in `spawn_agents` tool lets the orchestrator LLM fan work out to concurrent sub-agents. Each sub-agent is a fully separate `Agent` with its own isolated `Context` — it doesn't share history with the orchestrator or with other sub-agents. It runs to completion inside the tool call and returns its final text as the tool result. Sub-agents cannot spawn further sub-agents (the tool excludes itself from any sub-agent's tool set, so there's no recursion).

Wire it up like any other tool, but it needs the orchestrator's `LLM` and a name→tool map so it knows what it's allowed to hand out:

```python
from minimal_agent import Agent
from minimal_agent.llm import LLM
from minimal_agent.tools.builtin.grep import Grep
from minimal_agent.tools.builtin.glob import Glob
from minimal_agent.tools.builtin.read_file import ReadFile
from minimal_agent.tools.builtin.spawn_agents import SpawnAgents

llm = LLM(model="gpt-4o", backend="openai")
workspace = Path.cwd()

builtin_tools = [
    ReadFile(workspace_root=workspace, read_timestamps={}),
    Grep(workspace_root=workspace),
    Glob(workspace_root=workspace),
]
tools_by_name = {t.name: t for t in builtin_tools}

spawn_agents = SpawnAgents(
    llm=llm,                        # sub-agents reuse the orchestrator's LLM
    available_tools=tools_by_name,   # pool sub-agents can be given tools from
    workspace_root=workspace,
)

agent = Agent(
    llm=llm,
    tools=[*builtin_tools, spawn_agents],
    workspace_root=workspace,
)
```

The orchestrator LLM decides at call time how many sub-agents to spawn, what each one's task is, and which tools (by name) each gets — up to 10 concurrently. Each `SubAgentSpec` accepts:

| Field | Meaning |
|---|---|
| `task` | Self-contained instructions — the sub-agent sees *only* this task, no orchestrator history |
| `tools` | Tool names from `available_tools` to hand out; `None` gives it everything except `spawn_agents` itself |
| `max_turns` | Agent-loop turn cap for this sub-agent (1–20, default 5) |

Results come back concatenated, each labeled `[Sub-agent N: <task>]`, with failures captured inline as `ERROR: <type>: <message>` rather than raised — a crashing sub-agent doesn't take down the others or the orchestrator.

Every sub-agent is fully recorded under the session's `agents/` directory: its own transcript, timeline, and call audit, plus an `agent.json` naming who spawned it, its task, final status, and token usage. The parent session's timeline gains `agent.spawn` / `agent.end` events, and sub-agent usage rolls up into the session's totals — nothing an agent does in a session is off the record.

If you write your own tool that runs an agent inside it, ask the tool's scope for a child and you get the same recording:

```python
async def invoke(self, args, ctx: ToolContext) -> str:
    with ctx.scope.child(
        spawned_by=self.name, task=args.task, tool_call_id=ctx.tool_call_id
    ) as scope:
        context = scope.new_context(system_prompt=...)
        context.add(Message(role=Role.USER, content=args.task))
        async for msg in my_agent.run(context):
            ...
    return final_answer
```

The child scope allocates its directory, records the nested run end to end, and closes with a truthful status (`completed` / `error` / `abandoned`) even if the body raises. Under a bare `ToolContext()` (unit tests), the same code runs unrecorded.

### Reasoning

To turn on a model's reasoning ("thinking"), give the agent a `ReasoningConfig`. Providers differ on how you enable reasoning and what field the trace comes back on, so you supply both:

```python
from minimal_agent.llm import ReasoningConfig

agent = Agent(
    llm=llm,
    tools=[...],
    reasoning=ReasoningConfig(
        request_params={"reasoning_effort": "high"},  # how to turn thinking on
        response_field="reasoning",                   # where the trace comes back
    ),
)
```

The reasoning trace then rides on each assistant message as `message.reasoning` (and on streamed chunks as `chunk.reasoning`, arriving before the answer):

```python
async for message in agent.run(session.context):
    if message.role == Role.ASSISTANT:
        if message.reasoning:
            print("thinking:", message.reasoning)
        print("answer:", message.content)
```

Settings for common providers:

| Provider | `request_params` | `response_field` |
|---|---|---|
| OpenAI reasoning models (o-series, gpt-5.x) | `{"reasoning_effort": "high"}` | `"reasoning"` |
| OpenRouter | `{"reasoning_effort": "high"}` | `"reasoning"` |
| Qwen (DashScope) | `{"enable_thinking": True}` | `"reasoning_content"` |
| Local llama.cpp | `{}` — many models think by default | `"reasoning_content"` |

If `message.reasoning` comes back empty, the `response_field` usually doesn't match what your provider returns — try `reasoning_content` instead of `reasoning`, or vice versa.

### Observability

Sessions record what happens as they run — no wiring needed. Everything that happens in a session, including every sub-agent, lands in one directory tree:

```
.minimal_agent/sessions/<session-id>/
├── session.json     # identity, aggregate usage (sub-agents included)
├── messages.jsonl   # the conversation
├── events.jsonl     # the timeline: one timestamped event per line
├── calls.jsonl      # one provenance record per LLM call
├── blobs/           # content-addressed system prompts and tool schemas,
│                    # shared by every agent in the session
└── agents/          # one directory per nested agent
    └── a-3f9c21ab/
        ├── agent.json       # who spawned it, task, status, usage, model
        ├── messages.jsonl   # the sub-agent's full transcript
        ├── events.jsonl     # its own timeline
        └── calls.jsonl      # its own call audit
```

`events.jsonl` answers *"what happened, when?"* — a run started, a call took 2.7s and used 876 tokens, a tool was denied after 8 seconds of deliberation, a sub-agent was spawned and completed. `calls.jsonl` + `blobs/` answer *"what exactly did the model see?"* — every call's full input (system prompt, projected messages, injected live blocks, tool schemas) is reconstructible, byte-exactly, from the session directory alone. Both guarantees hold for every agent in the tree: a sub-agent's record is the same shape as the main agent's, just one directory down.

Read it back with the audit API:

```python
from minimal_agent import (
    find_agent_scope,
    reconstruct_call,
    run_summaries,
    single_run,
)

# The cheap index: one summary row per run (id, model, status, calls) —
# reads runs.jsonl, reconstructs nothing. Pick the run you want, then
# drill in.
for s in run_summaries(session.session_dir):
    print(s.run_id, s.status, f"{s.calls} calls")

# One run, fully expanded — its calls, each carrying its full input,
# response, latency, usage, tool executions, and any sub-agents it
# spawned. Returns None for an unknown run_id.
run = single_run(session.session_dir, "r-4c7d01ab")
for call in run.calls:
    print(f"  {call.call_id}: {call.latency_ms}ms, "
          f"{len(call.input.messages)} input messages")
    for agent in call.spawned_agents:
        print(f"    spawned {agent.agent_id}: {agent.task} → {agent.status}")

# A spawned sub-agent records the same kit under its own scope. Resolve it
# by id (at any nesting depth) and the same readers apply, one level down.
scope = find_agent_scope(session.session_dir, "a-1434198a")
for s in run_summaries(scope):
    sub_run = single_run(scope, s.run_id)

# Or one call's exact input, verified against its recorded hash. Works
# on the session root and on any agents/<id>/ directory alike.
call = reconstruct_call(session.session_dir, "r-4c7d01ab:c1")
assert call.verified
call.messages   # exactly what the model saw, in order
```

Recording is fire-and-forget — it can never fail or slow a run — and a bare in-memory `Context()` records nothing. Because system prompts and tool schemas are content-addressed, *"the agent behaves differently since yesterday"* is answered by diffing two blobs.

### System Prompt

The system prompt is built from three parts: a **behavior prompt** (markdown that defines the agent's personality), an **environment block** (workspace metadata), and **context blocks** (from SESSION-placed context sources, labeled as a session-start snapshot). The `system_prompt` module handles assembly — you just pass a markdown file or string. Volatile state like git status doesn't live here: it rides the message list, refreshed each run (see [Write a custom context source](#4-write-a-custom-context-source)).

### Skills

Skills are reusable prompt templates stored as markdown files on disk. Instead of baking every specialized instruction into the system prompt, you write a `SKILL.md` per task (e.g. "create a git commit", "review a PR") and the agent loads it on demand.

The model sees a lightweight list of available skills (just names + descriptions) in its system prompt. When one is relevant, it calls the built-in `skill` tool to load the full instructions. This is the same two-phase pattern Anthropic's own agents use — cheap metadata always, expensive prompt only when needed. See the official [Agent Skills Specification](https://agentskills.io/specification) for the file format.

Skills are auto-discovered when you pass `workspace_root` to the `Agent`. Drop a skill at `.minimal_agent/skills/<name>/SKILL.md` in your project (or `~/.minimal_agent/skills/` for user-level skills), and it shows up in the agent's skill list. Project-level skills shadow user-level skills with the same name.

## Building a Custom Agent

The default agent is a software engineer, but you can build anything. Here's a code review agent with a custom prompt and no shell access:

### 1. Write a behavior prompt

Create a markdown file — no special syntax, just instructions for the LLM.

```markdown
<!-- review_agent.md -->
You are a code review assistant. You help developers improve their code
by finding bugs, suggesting simplifications, and enforcing project conventions.

# Tool usage

- Use grep and glob to understand the codebase before commenting.
- Use read_file to see the full context of files mentioned in a review.
- Do not modify any files. You are read-only.

# Style

- Be direct. Say what's wrong, why, and how to fix it.
- Cite specific line numbers when pointing out issues.
```

### 2. Build the agent

Point the agent at your prompt file. Since this isn't a general coding agent, we skip the shell and write tools and explicitly choose our context sources.

```python
from pathlib import Path

from minimal_agent import Agent
from minimal_agent.context_sources import GitStatusSource
from minimal_agent.llm import LLM
from minimal_agent.tools.builtin.glob import Glob
from minimal_agent.tools.builtin.grep import Grep
from minimal_agent.tools.builtin.read_file import ReadFile


llm = LLM(model="gpt-4o", backend="openai")
workspace = Path.cwd()

agent = Agent(
    llm=llm,
    tools=[
        ReadFile(workspace_root=workspace, read_timestamps={}),
        Grep(workspace_root=workspace),
        Glob(workspace_root=workspace),
    ],
    prompt=Path("review_agent.md"),
    context_sources=[GitStatusSource()],  # git status but no directory tree
    workspace_root=workspace,
)
```

When you pass a custom `prompt`, context sources default to empty — you opt in to exactly what's relevant. The default agent (no `prompt` arg) auto-includes `GitStatusSource` and `DirectoryTreeSource`. `GitStatusSource` is RUN-placed, so the model sees the working tree as of the current turn rather than a snapshot frozen at session start.

### 3. Write a custom tool

Tools are just async classes with a Pydantic schema. Here's a minimal example:

```python
from pydantic import BaseModel, Field

from minimal_agent.tools.base import BaseTool
from minimal_agent.tools.context import ToolContext


class GreetInput(BaseModel):
    """Say hello to someone."""
    name: str = Field(..., description="The person's name")


class Greet(BaseTool[GreetInput, str]):
    name = "greet"
    input_schema = GreetInput

    async def invoke(self, args: GreetInput, ctx: ToolContext) -> str:
        return f"Hello, {args.name}!"

    def render_result_for_assistant(self, out: str) -> str:
        return out
```

The `input_schema` docstring becomes the tool description the LLM sees. Field descriptions become parameter descriptions. That's all the LLM needs to know how to call your tool.

**Optional hooks you can override:**

- `validate(args, ctx)` — reject bad inputs before execution
- `needs_permission(args)` — return `True` if this invocation needs user approval
- `render_result_for_assistant(out)` — control what the LLM sees as the tool result

### 4. Write a custom context source

Context sources gather dynamic information about the environment. Any object with a `name` property and an async `gather()` method works — no base class needed.

```python
from pathlib import Path


class PackageJsonSource:
    """Injects package.json contents into the system prompt."""

    @property
    def name(self) -> str:
        return "packageJson"

    async def gather(self, workspace_root: Path) -> str | None:
        pkg = workspace_root / "package.json"
        if not pkg.exists():
            return None
        return pkg.read_text()
```

Pass it to the agent:

```python
agent = Agent(
    llm=llm,
    tools=[...],
    context_sources=[PackageJsonSource(), GitStatusSource()],
    workspace_root=workspace,
)
```

The gathered content is wrapped as `<context name="packageJson">...</context>`. Where and when it's gathered is declared on the source itself, via an optional class-level `placement` (from `minimal_agent.context_sources`):

| `placement` | Gathered | Lands |
|---|---|---|
| `Placement.SESSION` (default) | Once, at session creation | System prompt, labeled as a snapshot |
| `Placement.RUN` | Once per `agent.run()` | Merged into that run's user message |
| `Placement.CALL` | Before every LLM call | Trailing message, refreshed each call |

Without a `placement` attribute, a source defaults to `Placement.SESSION` — gathered once, baked into the prompt. Declare `Placement.RUN` for state that changes between user turns (this is what the built-in `GitStatusSource` does); reserve `Placement.CALL` for state that must track the agent's own mid-run side effects — its content can never be prefix-cached, so it's re-sent on every call:

```python
from minimal_agent.context_sources import Placement


class PackageJsonSource:
    placement = Placement.RUN  # re-gathered at the start of each run
    ...
```

RUN/CALL content is injected at LLM-call time and never written to the session transcript. It reaches the conversation only for sessions created through `agent.create_session()` / `agent.load_session()`, which wire the agent's live sources into the session's `Context`.

### 5. Write a skill

Skills are markdown files with YAML frontmatter. The frontmatter gives the skill a name and a one-line description (this is what the model reads to decide when to use it); the body is the full prompt the model follows once the skill is invoked.

```markdown
<!-- .minimal_agent/skills/commit/SKILL.md -->
---
name: commit
description: Create a well-structured git commit with a conventional message. Use when the user asks to commit staged changes.
---

# Creating a commit

1. Run `git status` and `git diff --staged` to see what's being committed.
2. Write a commit message in conventional-commits style (`feat:`, `fix:`, `refactor:`, etc.).
3. Keep the subject under 72 characters. Add a body if the change needs context.
4. Run `git commit -m "<message>"` and report the resulting commit hash.
```

Two frontmatter fields are required:

- `name` — 1–64 chars, lowercase letters, numbers, and hyphens only. **Must match the parent directory name.**
- `description` — 1–1024 chars. This is what the model sees in the skill list, so make it specific enough that the model knows when to invoke the skill.

Optional fields (`license`, `compatibility`, `metadata`, `allowed-tools`) are described in the [official specification](https://agentskills.io/specification).

Skills are discovered from two roots, in priority order:

1. **Project-local:** `.minimal_agent/skills/<name>/SKILL.md` in the workspace root or any ancestor directory. A skill defined at the repo root is found from any subdirectory.
2. **User-level:** `~/.minimal_agent/skills/<name>/SKILL.md`. Available across every project.

Project-level skills shadow user-level skills with the same name (case-insensitive). Shadowed skills are still tracked so you can see what's being overridden.

#### Enabling skills

Skills are enabled automatically when you pass `workspace_root` to the `Agent`:

```python
agent = Agent(
    llm=llm,
    tools=[...],
    workspace_root=Path.cwd(),
)
```

The agent scans for skills once at construction, registers the built-in `skill` tool, and injects the skill list into the system prompt as a `<context name="availableSkills">` block. Pass `enable_skills=False` to opt out.

#### How the model uses a skill

The model reads the skill list in its system prompt, decides a skill matches the user's request, and calls the `skill` tool with the skill name. The tool reads the full `SKILL.md` from disk and returns its contents as the tool result. The model then follows those instructions for the rest of the turn.

This is progressive disclosure: the skill list costs ~100 tokens, but the full prompt is only loaded when it's actually needed. You can have dozens of skills available without paying the token cost of any specific one until the model decides to use it.

Skills can reference additional files (`scripts/`, `references/`, `assets/`) alongside the `SKILL.md` — the skill prompt just tells the model to read them with its existing tools. See the [official specification](https://agentskills.io/specification) for the full directory layout and progressive-disclosure pattern.