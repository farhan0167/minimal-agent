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

This directory is a small uv project ([pyproject.toml](pyproject.toml)) that depends on the sibling package `../minimal_agent`, installed **editable** — so changes to the library are picked up without reinstalling. Sync the environment:

```bash
uv sync
```

From a source checkout also build the UI once (`make ui` at the repo root — needs Node) before serving the chat UI; installs from a released wheel ship the UI prebuilt.

> Prefer plain pip / the PyPI release instead? `pip install "mini-agent-kit[server]"` also works — the scripts only import the installed package.

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
uv run my_app.py
```

Open `http://localhost:8000`. The API docs live at `/docs`, endpoints under `/api`.

## It's just FastAPI

`App` subclasses `FastAPI`, so everything FastAPI works: add routes and middleware, pass a `lifespan`, or run it with uvicorn directly — including hot reload, which `serve()` itself can't do (it holds a live object):

```bash
uvicorn my_app:app --reload
```

## Adding an agent

Construct another `Agent` — its tools, prompt, and workspace are the configuration — and add it to the `agents` dict. It appears in the UI's agent picker on restart. Each session remembers which agent it belongs to and routes back to it on resume.
