# Research Agent

A research agent served in the browser: web search plus read-only file access —
no writing, no shell. Its behavior prompt ([behavior.md](behavior.md)) shapes it
toward finding, corroborating, and citing sources. It also turns on the model's
**reasoning** ("thinking"), streamed to the chat UI as a collapsible block. The
whole thing is [main.py](main.py).

## Run it

```bash
cp .env.example .env    # then edit — set OPENROUTER_API_KEY (and TAVILY_API_KEY)
uv sync
uv run main.py
```

Open http://localhost:8000. API docs at `/docs`, endpoints under `/api`.

> `uv sync` installs `mini-agent-kit` editable from the sibling `../../minimal_agent`
> checkout. From a source checkout, also build the UI once with `make ui` at the
> repo root (needs Node); released wheels ship it prebuilt. Prefer the PyPI
> release? `pip install "mini-agent-kit[server]"` works too.

## Reasoning

Reasoning is opt-in and provider-specific, so you declare the contract in
[main.py](main.py):

```python
reasoning = ReasoningConfig(response_field="reasoning")
```

`response_field` is the field the trace comes back on — `"reasoning"` for
OpenRouter, `"reasoning_content"` for Qwen/DeepSeek. If your model or backend
doesn't reason, delete the `ReasoningConfig` and drop `reasoning_config=` from
the `LLM(...)` call.

## It's just FastAPI

`App` subclasses `FastAPI`, so add routes/middleware, pass a `lifespan`, or run
with uvicorn directly for hot reload:

```bash
uvicorn main:app --reload
```
