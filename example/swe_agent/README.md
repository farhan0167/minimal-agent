# SWE Agent

A software-engineer agent served in the browser: file read/write/edit, shell,
search, web, and sub-agent spawning — the full toolset. The whole thing is
[main.py](main.py).

## Run it

```bash
cp .env.example .env    # then edit — set OPENAI_API_KEY (and TAVILY_API_KEY)
uv sync
uv run main.py
```

Open http://localhost:8000. API docs at `/docs`, endpoints under `/api`.

> `uv sync` installs `mini-agent-kit` editable from the sibling `../../minimal_agent`
> checkout. From a source checkout, also build the UI once with `make ui` at the
> repo root (needs Node); released wheels ship it prebuilt. Prefer the PyPI
> release? `pip install "mini-agent-kit[server]"` works too.

## It's just FastAPI

`App` subclasses `FastAPI`, so add routes/middleware, pass a `lifespan`, or run
with uvicorn directly for hot reload (which `serve()` can't do):

```bash
uvicorn main:app --reload
```
