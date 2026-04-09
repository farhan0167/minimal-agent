# Example: Chat Web App

A full-stack chat application built on top of `minimal-agent`. It pairs a **FastAPI server** that exposes the agent over HTTP/SSE with a **React frontend** for an interactive chat UI.

## Architecture

```
server/          FastAPI backend — sessions, streaming chat via SSE
web/             React + Vite + TypeScript frontend
```

The frontend sends messages to the server, which runs the agent loop and streams responses back as Server-Sent Events. Sessions are persisted to disk as JSON so conversations survive restarts.

### API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions` | Create a new session (requires `workspace_root`) |
| `GET` | `/sessions` | List all sessions |
| `GET` | `/sessions/{id}` | Get a single session |
| `DELETE` | `/sessions/{id}` | Delete a session |
| `POST` | `/sessions/{id}/chat` | Send a message and stream the response (SSE) |
| `GET` | `/sessions/{id}/messages` | Get message history |
| `GET` | `/tools` | List available tools |
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
python main.py   # runs on http://localhost:8000 with hot reload
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
2. Create a new session — provide an absolute path to the workspace directory the agent should operate in
3. Chat with the agent

The agent has access to all built-in tools: file read/write/edit, shell commands, glob, grep, web search, and more. Tool calls and their results are displayed inline in the chat UI.
