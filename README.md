# Minimal Agent

A minimal async agent framework in Python. An agent loop drives an LLM that can call tools, with provider details abstracted behind a provider-agnostic facade.

![Architecture diagram](docs/images/agent-loop.png)

## Install

Requires Python >= 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
cd minimal_agent
uv sync
```

Copy `.env.example` to `.env` and set your API key:

```bash
cp .env.example .env
# Edit .env — set LLM_BACKEND and LLM_BACKEND_API_KEY
```

| Backend | `LLM_BACKEND` | Notes |
|---|---|---|
| OpenAI | `openai` | Default. Uses `gpt-4o-mini` by default |
| Anthropic | `anthropic` | Via OpenAI-compatible endpoint |
| OpenRouter | `openrouter` | Any model on OpenRouter |
| Local server | `localhost` | vLLM, llama.cpp, LM Studio, Ollama — set `LLM_BACKEND_BASE_URL` |

## Build your own agent

`minimal_agent` is an installable library. You create a new project that depends on it, wire up the tools you want, and run it however you like.

### 1. Create a new project

```
my_project/
  main.py
  pyproject.toml
```

In `pyproject.toml`, add `minimal_agent` as a dependency (path reference to the local package):

```toml
[project]
name = "my-project"
requires-python = ">=3.11"
dependencies = [
    "minimal-agent",
]

[tool.uv.sources]
minimal-agent = { path = "../minimal_agent" }
```

### 2. Set up the LLM and agent

```python
# main.py
import asyncio
from pathlib import Path

from minimal_agent import Agent, Session, Settings
from minimal_agent.llm import LLM
from minimal_agent.tools.builtin.read_file import ReadFile
from minimal_agent.tools.builtin.run_shell import RunShell

settings = Settings()
workspace = Path.cwd()

llm = LLM(
    model=settings.LLM_MODEL,
    backend=settings.LLM_BACKEND,
)

agent = Agent(
    llm=llm,
    tools=[
        ReadFile(workspace_root=workspace),
        RunShell(workspace_root=workspace),
    ],
)


async def main():
    system_prompt = await agent.build_system_prompt(workspace_root=workspace)
    session = Session.create(
        model=settings.LLM_MODEL,
        backend=settings.LLM_BACKEND,
        system_prompt=system_prompt,
    )

    # Add a user message
    from minimal_agent.llm import Message, Role
    session.context.add(Message(role=Role.USER, content="List the files in this directory"))

    # Run the agent loop
    async for message in agent.run(session.context):
        if message.role == Role.ASSISTANT and message.content:
            print(message.content)

asyncio.run(main())
```

That's a working agent. It reads the user message, calls the LLM, uses tools if needed, and prints the response.

### 3. Add your own tools

Create a tool by subclassing `BaseTool`. A tool needs three things: a name, a Pydantic input schema, and an `invoke` method.

```python
from pydantic import BaseModel, Field
from minimal_agent.tools.base import BaseTool
from minimal_agent.tools.context import ToolContext


class LookupInput(BaseModel):
    """Look up a customer by email."""
    email: str = Field(..., description="Customer email address")


class LookupCustomer(BaseTool[LookupInput, str]):
    name = "lookup_customer"
    input_schema = LookupInput

    def __init__(self, db):
        self._db = db

    async def invoke(self, args: LookupInput, ctx: ToolContext) -> str:
        customer = await self._db.find_by_email(args.email)
        if not customer:
            return "No customer found"
        return f"Found: {customer.name} (id={customer.id})"
```

Then pass it to your agent:

```python
agent = Agent(
    llm=llm,
    tools=[
        LookupCustomer(db=my_database),
        ReadFile(workspace_root=workspace),
    ],
)
```

The model sees the tool's name, the docstring on the input schema (as the tool description), and the field descriptions. That's all it needs to decide when and how to call it.

### Optional hooks

Override these methods on `BaseTool` for more control:

- **`needs_permission(args)`** — Return `True` to require user confirmation before execution. Use for destructive operations.
- **`validate(args)`** — Semantic validation beyond what Pydantic checks (e.g., "file must exist"). Return `ValidationOk()` or `ValidationErr("reason")`.
- **`render_result_for_assistant(result)`** — Customize what the model sees after the tool runs. Default is `str(result)`.

### 4. Custom system prompts

By default, the agent uses a built-in software engineering prompt. Pass your own:

```python
agent = Agent(
    llm=llm,
    tools=[...],
    prompt="You are a customer support agent. Be helpful and concise.",
)
```

Or point to a markdown file:

```python
agent = Agent(
    llm=llm,
    tools=[...],
    prompt=Path("prompts/support_agent.md"),
)
```

### 5. Context sources

Context sources inject dynamic information into the system prompt (git status, directory trees, or anything you define). Implement the `ContextSource` protocol:

```python
from minimal_agent.system_prompt import ContextSource

class DatabaseSchemaSource:
    name = "db_schema"

    async def gather(self, workspace_root) -> str:
        # Return whatever context you want injected
        return "Tables: users, orders, products ..."

agent = Agent(
    llm=llm,
    tools=[...],
    prompt="You are a database assistant.",
    context_sources=[DatabaseSchemaSource()],
)
```

## Repo structure

```
minimal_agent/              # Core library (installable package, src layout)
  src/minimal_agent/
    agent/                  # Agent loop, context, sessions
    llm/                    # Provider-agnostic LLM facade
    system_prompt/          # System prompt builder + context sources
    tools/                  # Tool system (base class, dispatcher, builtins)
    config.py               # Settings via pydantic-settings
cli/                        # Terminal client (Rich + prompt-toolkit)
streamlit_client/           # Streamlit web client
```

### Built-in tools

`read_file`, `write_file`, `edit_file`, `glob`, `grep`, `run_shell`, `spawn_agents`, `web_search`, `web_extract`, `get_weather` (stub)

## Development

```bash
cd minimal_agent
make format    # ruff format
make lint      # ruff check
make test      # pytest
```
