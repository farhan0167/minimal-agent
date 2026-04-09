# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- **Dev server:** `npm run dev` (Vite, serves on localhost:5173)
- **Build:** `npm run build` (runs `tsc -b && vite build`, output in `dist/`)
- **Lint:** `npm run lint` (ESLint with TypeScript + React hooks rules)
- **Preview production build:** `npm run preview`

No test framework is configured.

## Backend Proxy

Vite proxies `/api/*` to `http://localhost:8000` (stripping the `/api` prefix). The FastAPI backend must be running separately for the app to function. In production, set `VITE_API_BASE_URL` to the server's URL.

## Architecture

This is a React + TypeScript chat frontend for the `minimal-agent` project. It uses `@assistant-ui/react` as the chat UI framework with a custom `LocalRuntime` adapter that streams messages via SSE from a FastAPI backend.

### Key layers

- **`api/`** — HTTP and SSE client functions. `client.ts` provides `apiFetch` (base URL + error handling wrapper). `chat.ts` streams agent responses as SSE via `sendMessage` async generator. `sessions.ts` handles CRUD for chat sessions.
- **`lib/sse.ts`** — Pure async generator that parses raw SSE text streams into typed `SSEEvent` objects (event types: `assistant`, `tool_result`, `error`, `done`).
- **`hooks/use-chat-runtime.ts`** — The central integration layer. Converts flat server message history into assistant-ui's `ThreadMessageLike` format (merging assistant+tool messages into single turns), and wires up the SSE streaming adapter for `useLocalRuntime`.
- **`hooks/use-sessions.ts`** — Session state management (list, create, select, delete).
- **`components/tools/`** — Tool call rendering system. `index.tsx` registers a `makeAssistantToolUI` for each known tool name. To add a new tool, append its name to the `TOOL_NAMES` array. `ToolCallRenderer` is the fallback collapsible JSON viewer for args/results.
- **`types/`** — Shared TypeScript interfaces mirroring the backend API schema (`Message`, `Session`, `SSEEvent`, etc.).

### Styling

Tailwind CSS v4 via `@tailwindcss/vite` plugin. No separate Tailwind config file — uses CSS-based configuration in `index.css`. The app uses a warm off-white palette (`#f5f5f0` background, `#1a1a18` text, `#ae5630` accent).

### SSE message flow

1. User sends message → `POST /sessions/{id}/chat` with SSE response
2. `parseSSEStream` yields typed events from the raw stream
3. `useChatRuntime` adapter accumulates content parts (text + tool calls with results) and yields cumulative snapshots to assistant-ui's runtime
4. On session load, `getMessages` fetches history and `toThreadMessages` reconstructs the thread
