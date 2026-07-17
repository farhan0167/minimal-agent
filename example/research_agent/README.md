# Research Agent

A research agent served in the browser: web search plus read-only file access —
no writing, no shell. Its behavior prompt ([behavior.md](behavior.md)) shapes it
toward finding, corroborating, and citing sources. It also turns on the model's
**reasoning** ("thinking"), streamed to the chat UI as a collapsible block. The
whole thing is [main.py](main.py).

It also connects to **MCP servers**: create a `.minimal_agent/mcp.json` next
to where you run it, in the standard `mcpServers` format MCP marketplaces
publish, and its tools are discovered at startup and handed to the agent
(named `mcp__<server>__<tool>`). The file is required — startup fails fast
with a `FileNotFoundError` if it's missing. For example, to give the
researcher Notion access:

```json
{
  "mcpServers": {
    "notionApi": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": { "NOTION_TOKEN": "${NOTION_SECRET}" }
    }
  }
}
```

`${VAR}` references are expanded from your environment (or `.env`) at load
time — startup fails fast if one is unset — so tokens never live in the file.

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

`App` subclasses `FastAPI`, so you can add routes and middleware as usual. One
difference from the swe_agent example: the app is constructed and served
*inside* `MCPToolProvider`'s `async with` block, because the provider owns the
MCP server connections and must stay open for the agent's whole life. That's
why [main.py](main.py) serves with the async `await app.a_serve()` instead of
the blocking `app.serve()` (which would try to own its own event loop), and
why `uvicorn main:app --reload` doesn't apply here (there is no module-level
`app` to point it at).
