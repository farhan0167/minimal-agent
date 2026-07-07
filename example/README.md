# Example: Serving Agents with `App`

[my_app.py](my_app.py) is the whole example: two agents — a **software engineer** (file read/write/edit, shell, search, sub-agent spawning) and a **researcher** (web search, read-only file access) — registered on one `App` and served from one process.

```python
from minimal_agent import Agent, App

app = App(agents={"swe": swe_agent, "research": research_agent})

if __name__ == "__main__":
    app.serve()  # → http://localhost:8000 — API + chat web UI
```

The UI's new-session dialog shows both agents with their workspace, model, and toolset; pick one and chat. With a single registered agent (`App(agents=my_agent)`) the dialog disappears entirely — "New Session" just creates one.

## Prerequisites

- Python 3.11+
- An API key for your chosen LLM backend
- Optional: PDF attachment support needs the `pdf` extra (`pip install "mini-agent-kit[server,pdf]"`) plus system [Poppler](https://poppler.freedesktop.org/) (`sudo apt-get install poppler-utils` / `brew install poppler`)

## Run it

This directory is its own tiny project — [pyproject.toml](pyproject.toml) depends on `mini-agent-kit[server,phoenix]` and resolves it from the sibling checkout (`../minimal_agent`), installed **editable** so your local edits to the framework are picked up without a reinstall. Sync it once:

```bash
uv sync          # installs the local package + server & phoenix extras into ./.venv
```

From a source checkout also build the UI once (`make ui` at the repo root — needs Node); installs from a released wheel ship the UI prebuilt.

> Prefer plain pip, or testing against a published release instead of the local checkout? Skip the sync and `pip install "mini-agent-kit[server]"` — then run the commands below with `python` instead of `uv run`. To point the example at PyPI instead of the local path, delete the `[tool.uv.sources]` block in `pyproject.toml`.

Configure the LLM via environment variables or a `.env` file in this directory:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | API key (or dummy value like `sk-local` for local servers) |
| `LLM_MODEL` | Yes | Model name, e.g. `gpt-4o-mini` |
| `LLM_BACKEND` | No | `openai` (default), `anthropic`, `openrouter`, or `localhost` |
| `OPENAI_BASE_URL` | No | Override for OpenAI-compatible servers (vLLM, llama.cpp, Ollama) |
| `TAVILY_API_KEY` | No | Enables `web_search` and `web_extract` tools |
| `SESSIONS_DIR` | No | Where to store session data (defaults to `.minimal_agent/sessions`) |

Then:

```bash
uv run python my_app.py
```

Open `http://localhost:8000`. The API docs live at `/docs`, endpoints under `/api`.

## Phoenix tracing (optional)

The `phoenix` extra is already installed by `uv sync`. Start a local [Phoenix](https://arize.com/docs/phoenix) listening on `:6006`, then set `PHOENIX=1`:

```bash
PHOENIX=1 uv run python my_app.py
```

Every run streams to Phoenix as OpenTelemetry spans — a `CHAIN` span per run owning its `LLM` calls, `TOOL` dispatches, and any spawned sub-agents, nested as they ran. Leave `PHOENIX` unset and the app behaves exactly as before (no sink, no extra imports touched). Spans are flushed on a clean exit; Phoenix is a browsable mirror, while the local `.minimal_agent/sessions/` directory stays the source of truth.

By default the spans carry timing, token counts, and nesting — but not the prompt. To also see **what the model saw** (system prompt + messages, reconstructed from the local artifacts and flattened onto each `LLM` span), add `PHOENIX_FULL=1`:

```bash
PHOENIX=1 PHOENIX_FULL=1 uv run python my_app.py
```

That costs a per-call blob read and sends prompt content off-box to Phoenix, so it's opt-in.

## It's just FastAPI

`App` subclasses `FastAPI`, so everything FastAPI works: add routes and middleware, pass a `lifespan`, or run it with uvicorn directly — including hot reload, which `serve()` itself can't do (it holds a live object):

```bash
uvicorn my_app:app --reload
```

## Adding an agent

Construct another `Agent` — its tools, prompt, and workspace are the configuration — and add it to the `agents` dict. It appears in the UI's agent picker on restart. Each session remembers which agent it belongs to and routes back to it on resume.
