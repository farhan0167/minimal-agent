# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- **Dev server:** `npm run dev` (Vite, serves on localhost:5173)
- **Build:** `npm run build` (runs `tsc -b && vite build`, output in `dist/`)
- **Lint:** `npm run lint` (ESLint with TypeScript + React hooks rules)
- **Preview production build:** `npm run preview`

No test framework is configured.

## Backend Proxy

Vite proxies `/api/*` to `http://localhost:8000` (prefix preserved — the backend serves under `/api`). The FastAPI backend must be running separately for the app to function. In production, set `VITE_API_BASE_URL` to the server's URL.

## Architecture

This is a React + TypeScript chat frontend for the `minimal-agent` project. It uses `@assistant-ui/react` as the chat UI framework with a custom `LocalRuntime` adapter that streams messages via SSE from a FastAPI backend.

### Key layers

- **`api/`** — HTTP and SSE client functions. `client.ts` provides `apiFetch` (base URL + error handling wrapper). `chat.ts` streams agent responses as SSE via `sendMessage` async generator. `sessions.ts` handles CRUD for chat sessions.
- **`lib/sse.ts`** — Pure async generator that parses raw SSE text streams into typed `SSEEvent` objects (event types: `delta`, `assistant`, `tool_result`, `error`, `done`). `delta` carries streamed assistant text token-by-token; the following `assistant` event carries the committed full text (authoritative).
- **`hooks/use-chat-runtime.ts`** — The central integration layer. Converts flat server message history into assistant-ui's `ThreadMessageLike` format (merging assistant+tool messages into single turns), and wires up the SSE streaming adapter for `useLocalRuntime`.
- **`hooks/use-sessions.ts`** — Session state management (list, create, select, delete).
- **`components/chat/`** — The chat surface, built directly on `@assistant-ui/react` primitives (no prebuilt/styled vendor components). `Thread.tsx` owns the shell (viewport, message list, sticky composer footer); `Composer.tsx`/`EditComposer.tsx` the input forms; `AssistantMessage.tsx`/`UserMessage.tsx` the per-role message bodies via `MessagePrimitive.Parts` slots (`Text`, `Reasoning`, `Image`); `MarkdownText.tsx` the markdown renderer (`MarkdownTextPrimitive` + Shiki + per-language fence renderers). Structural styles live in `index.css` under "chat chrome" (`.chat-*` classes).
- **`components/tools/`** — Tool call rendering system. `index.tsx` registers a `makeAssistantToolUI` for each tool name fetched from `GET /tools`. `registry.ts` maps tool names to dedicated renderers (file, shell, search, web tools); `ToolCallRenderer` is the generic fallback. All renderers compose the `ToolCallCard` shell. See `README.md` — "Writing a renderer for a new tool".
- **`types/`** — Shared TypeScript interfaces mirroring the backend API schema (`Message`, `Session`, `SSEEvent`, etc.).

### Styling

Tailwind CSS v4 via `@tailwindcss/vite` plugin — no separate config file; CSS-based configuration lives in `index.css`.

Styling is a four-floor system, each floor reaching only one floor down:

- **features** (`components/chat · session · layout · tools`) compose primitives and pass props — **no** color/shape/font classes, no hex.
- **primitives** (`components/ui/`) are the only place raw Tailwind utilities touch tokens; each decides what a widget *is* (padding, radius, focus ring) once.
- **tokens** — `tokens.css` names every `--app-*` role (no values), and `index.css`'s `@theme` bridge exposes them as utilities (`bg-app-surface`, `rounded-ctl`, `font-prose`).
- **themes** (`themes/*.css` + `*.ts`) hold the actual values, filling every token for light and dark. Identity (`data-theme`) and mode (`.dark`) are independent axes on `<html>`.

`npm run check:tokens` fails the build on raw hex, Tailwind palette classes, `bg-[hsl(var(…))]`, or `font-serif` outside `components/ui/` and `themes/`.

To add a theme or a primitive, read **[docs/design-system.md](docs/design-system.md)** — it is the maintainer's guide to this system.

### SSE message flow

1. User sends message → `POST /sessions/{id}/chat` with SSE response
2. `parseSSEStream` yields typed events from the raw stream
3. `useChatRuntime` adapter accumulates content parts (text + tool calls with results) and yields cumulative snapshots to assistant-ui's runtime
4. On session load, `getMessages` fetches history and `toThreadMessages` reconstructs the thread
