# Examples

Two self-contained, runnable starting points. Each is one `main.py` that wires
up an `Agent`, hands it to an `App`, and serves it — API plus bundled chat web
UI — from one process on one port.

| Example | What it is |
|---|---|
| [swe_agent/](swe_agent/) | A software engineer: file read/write/edit, shell, search, web, sub-agents |
| [research_agent/](research_agent/) | A researcher: web search + read-only files, reasoning turned on, MCP servers loaded from `.minimal_agent/mcp.json` when present |

## Quick start

Pick one, then:

```bash
cd swe_agent            # or research_agent
cp .env.example .env    # then edit — set your API key
uv sync
uv run main.py          # → http://localhost:8000
```

Each directory has its own README with the details.

## The shape

Every example follows the same three lines you'll find in the top-level
[README](../README.md):

```python
llm = LLM(model="gpt-4o-mini", backend="openai", api_key=os.environ["OPENAI_API_KEY"])
agent = Agent(llm=llm, tools=[...], workspace_root=Path.cwd())
app = App(agents=agent)
```

Values are read straight from the environment or written inline — no config
indirection. Change the tools, the model, or the prompt and you have a
different agent.
