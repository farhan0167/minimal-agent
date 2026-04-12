# Example: Chat Web App

A full-stack chat application built on top of `minimal-agent`. It pairs a **FastAPI server** that exposes the agent over HTTP/SSE with a **React frontend** for an interactive chat UI.

## Architecture

```
server/
├── agents/          Agent modules — each subdirectory is a self-contained agent
│   ├── swe/         Software engineering agent (file ops, shell, search, etc.)
│   ├── research/    Research agent (read-only file access, web search)
│   └── ...          Drop a new folder here to add an agent
├── routes/          FastAPI route handlers
├── app.py           Session wiring, workspace validation, agent dispatch
├── schemas.py       Request/response models
└── main.py          Server entrypoint

web/                 React + Vite + TypeScript frontend
```

### Multi-agent design

The server supports multiple agent types. Each agent is a Python module under `server/agents/` that implements the `AgentConfig` protocol:

- `name` / `display_name` — identifier and human-readable label
- `build_agent()` — constructs an `Agent` with its own tools, system prompt, and configuration
- `get_tool_names()` — returns the list of tools this agent uses

Agent discovery is automatic — the server scans `agents/` subdirectories for modules containing an `agent.py` file. Adding a new agent requires no server code changes, just a new directory.

Agent type is selected at session creation time and persisted in a sidecar file (`agent_type.json`) alongside the library-owned `session.json`. This keeps the `minimal_agent` library untouched while allowing the server to track which agent a session belongs to.

### API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/agents` | List available agent types |
| `POST` | `/sessions` | Create a new session (requires `workspace_root` and `agent_type`) |
| `GET` | `/sessions` | List all sessions |
| `GET` | `/sessions/{id}` | Get a single session |
| `DELETE` | `/sessions/{id}` | Delete a session |
| `POST` | `/sessions/{id}/chat` | Send a message and stream the response (SSE) |
| `GET` | `/sessions/{id}/messages` | Get message history |
| `GET` | `/tools?agent_type=swe` | List tools for a given agent type |
| `GET` | `/health` | Health check |

### SSE event types

The `/sessions/{id}/chat` endpoint streams events with these types:

- `assistant` — text content from the model
- `tool_result` — result of a tool call
- `error` — an error occurred
- `done` — stream is complete

## Prerequisites

- Python 3.11+ with [uv](https://docs.astral.sh/uv/)
- Node.js 18+
- An API key for your chosen LLM backend
- [Poppler](https://poppler.freedesktop.org/) — required for PDF attachment support (`pdf2image` uses it to render pages)
  - **Debian/Ubuntu:** `sudo apt-get install poppler-utils`
  - **macOS:** `brew install poppler`

## Setup

### 1. Server

```bash
cd server
uv sync
```

Create a `.env` file (use the existing one as a template) and configure:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | API key (or dummy value like `sk-local` for local servers) |
| `LLM_MODEL` | Yes | Model name, e.g. `gpt-4o-mini` |
| `LLM_BACKEND` | No | `openai` (default), `anthropic`, `openrouter`, or `localhost` |
| `OPENAI_BASE_URL` | No | Override for OpenAI-compatible servers (vLLM, llama.cpp, Ollama) |
| `TAVILY_API_KEY` | No | Enables `web_search` and `web_extract` tools |
| `SESSIONS_DIR` | No | Where to store session data (defaults to `.minimal_agent/sessions`) |
| `ALLOWED_WORKSPACES` | No | Comma-separated allowed workspace paths (unrestricted if unset) |

Start the server:

```bash
uv run python main.py   # runs on http://localhost:8000 with hot reload
```

### 2. Frontend

```bash
cd web
npm install
npm run dev      # runs on http://localhost:5173
```

The Vite dev server proxies `/api/*` requests to the backend on port 8000, so both need to be running.

For production builds:

```bash
npm run build    # outputs to dist/
npm run preview  # preview the production build
```

Set `VITE_API_BASE_URL` to point at your server when deploying separately.

## Usage

1. Open `http://localhost:5173`
2. Create a new session — select an agent type and provide an absolute path to the workspace directory the agent should operate in
3. Chat with the agent

Each agent has access to a different set of tools depending on its purpose. The SWE agent includes file read/write/edit, shell commands, glob, grep, web search, and sub-agent spawning. The research agent is read-only with web search capabilities. Tool calls and their results are displayed inline in the chat UI.

## Adding a new agent

1. Create a new directory under `server/agents/` (e.g. `server/agents/my_agent/`)
2. Add an `__init__.py` and an `agent.py` that exports a `config` object implementing `AgentConfig`
3. Restart the server — the new agent appears in the frontend dropdown automatically

See `server/agents/swe/agent.py` for a full example.
