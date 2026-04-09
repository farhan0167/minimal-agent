# Web Frontend — How It Works

This doc walks through the `web/` codebase so you can understand what every piece does, how they connect, and where to make changes when you want to extend it.

## What This App Is

A chat UI for the `minimal-agent` backend. You create sessions, pick a model/backend, and chat with an AI agent that can call tools (read files, run shell commands, search the web, etc.). The frontend streams the agent's responses in real time using Server-Sent Events (SSE).

The backend is a separate FastAPI server that runs on port 8000. The frontend doesn't know or care about the agent logic — it just sends messages and renders whatever the server streams back.

## The Big Picture

```
┌─────────────────────────────────────────────────────────────┐
│  App                                                        │
│  ┌──────────────┐  ┌────────────────────────────────────┐   │
│  │   Sidebar     │  │  Main Area                         │   │
│  │              │  │  ┌──────────────────────────────┐   │   │
│  │  NewSession  │  │  │  Header (model, backend,     │   │   │
│  │  Dialog      │  │  │         token count)          │   │   │
│  │              │  │  ├──────────────────────────────┤   │   │
│  │  SessionList │  │  │                              │   │   │
│  │   └ Session  │  │  │  ChatPanel                   │   │   │
│  │     Item     │  │  │   (assistant-ui Thread)      │   │   │
│  │   └ Session  │  │  │   + tool call renderers      │   │   │
│  │     Item     │  │  │                              │   │   │
│  │              │  │  │  ── or ──                     │   │   │
│  │              │  │  │                              │   │   │
│  │              │  │  │  WelcomeScreen               │   │   │
│  └──────────────┘  │  └──────────────────────────────┘   │   │
│                    └────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

There are four systems at play:

1. **Session management** — creating, listing, selecting, and deleting chat sessions.
2. **The API layer** — all HTTP calls and SSE stream parsing.
3. **The chat runtime** — the bridge between the API layer and the UI library that renders messages.
4. **Tool call rendering** — how the agent's tool calls (like "read_file" or "run_shell") show up in the chat.

The rest of this doc explains each one.

---

## 1. Session Management

**Files:** `hooks/use-sessions.ts`, `api/sessions.ts`, `types/session.ts`

A "session" is a conversation with the agent. It has a model, a backend (openai/anthropic/openrouter/localhost), a workspace path on the server's filesystem, and token usage stats.

### How it flows

`App.tsx` calls `useSessions()`, which returns the session list, the active session, and functions to create/select/delete sessions.

On mount, `useSessions` calls `listSessions()` → `GET /sessions` to fetch all existing sessions. When the user clicks "New Session" in the sidebar, the `NewSessionDialog` collects a workspace path, model, and backend, then calls `createSession()` → `POST /sessions`. That session gets prepended to the list and becomes active.

Selecting a session just sets `activeSessionId` in React state. Deleting calls `DELETE /sessions/{id}` and removes it from the list.

### Where state lives

All session state is in the `useSessions` hook via `useState`. There's no global store, no context provider, no Redux. The hook returns everything, and `App.tsx` passes pieces down as props to the sidebar and header.

### If you want to extend this

- **Add a field to sessions** (like a name or description): update the `Session` type in `types/session.ts`, update `CreateSessionRequest` if it's user-provided, update `NewSessionDialog` to collect it, and update `SessionItem` to display it. The backend also needs to support it.
- **Persist the active session across page reloads**: save `activeSessionId` to `localStorage` in `useSessions`.

---

## 2. The API Layer

**Files:** `api/client.ts`, `api/chat.ts`, `api/sessions.ts`, `lib/sse.ts`, `lib/constants.ts`

### Base URL and proxying

`constants.ts` exports `API_BASE_URL`, which defaults to `/api`. In development, Vite intercepts requests to `/api/*` and proxies them to `http://localhost:8000`, stripping the `/api` prefix. So a frontend request to `/api/sessions` hits `http://localhost:8000/sessions` on the backend.

In production, you set the `VITE_API_BASE_URL` env var to point directly at the backend.

### apiFetch — the HTTP wrapper

`client.ts` exports `apiFetch(path, init?)`. It prepends the base URL and handles errors: if the response isn't OK and the body is JSON, it extracts the `detail` field and throws an `ApiError` with the status code. Every non-streaming API call goes through this.

### Session CRUD

`api/sessions.ts` is straightforward REST: `createSession`, `listSessions`, `getSession`, `deleteSession`. All use `apiFetch`.

### Chat — streaming with SSE

This is the most important part of the API layer. When the user sends a message, the app needs to stream the response in real time because the agent might take a while (it's calling tools, thinking, etc.).

`api/chat.ts` exports `sendMessage(sessionId, message, signal)`. It's an **async generator** — a function that yields values over time rather than returning once. It does:

1. `POST /sessions/{id}/chat` with `{ message }`. The response is an SSE stream, not a JSON blob.
2. Passes the response to `parseSSEStream()`, which yields parsed events as they arrive.

### How SSE parsing works

`lib/sse.ts` contains `parseSSEStream`, another async generator. SSE is a simple text protocol: events are separated by double newlines, and each event has an `event:` line and a `data:` line. For example:

```
event: assistant
data: {"role":"assistant","content":"Hello","tool_calls":null}

event: tool_result
data: {"role":"tool","content":"file contents here","tool_call_id":"abc123"}

event: done
data: {"usage":{"prompt_tokens":100,"completion_tokens":50,"total_tokens":150}}
```

The parser reads chunks from the response body stream, buffers them, splits on `\n\n`, parses each block's event type and JSON data, and yields typed `SSEEvent` objects. The four event types are:

- `assistant` — the agent produced text or is about to call tools
- `tool_result` — a tool finished and returned its result
- `error` — something went wrong
- `done` — the agent finished its turn

### If you want to extend this

- **Add a new API endpoint**: add a function in the appropriate `api/` file using `apiFetch`.
- **Handle a new SSE event type**: add it to the `SSEEvent` union in `types/message.ts`, handle it in the `switch` statement in `sse.ts`'s `parseSSEBlock`, and consume it in `use-chat-runtime.ts`.

---

## 3. The Chat Runtime

**Files:** `hooks/use-chat-runtime.ts`, `components/chat/ChatPanel.tsx`

This is the bridge between the API layer and `assistant-ui`, the library that renders the chat thread. It's the trickiest part of the code, so let's take it slow.

### What assistant-ui expects

`assistant-ui` provides a `<Thread />` component that renders a chat conversation. But it doesn't know how to talk to your backend. You give it a "runtime" — an object that tells it how to send messages and what the conversation history looks like. This app uses `useLocalRuntime`, which means the frontend controls the message flow (as opposed to a remote runtime where assistant-ui talks to a backend directly).

`useLocalRuntime` takes two things:
- A **ChatModelAdapter** with a `run()` method that the library calls when the user sends a message.
- **initialMessages** to pre-populate the thread (for loading history).

### The adapter's run() method

When the user types a message and hits send, assistant-ui calls `adapter.run()`. The adapter is defined in `useChatRuntime`:

1. It extracts the user's text from the message parts.
2. It calls `sendMessage(sessionId, userText, abortSignal)` to start the SSE stream.
3. It iterates over the SSE events and **yields cumulative snapshots** of the assistant's response.

That last point is important: each `yield` must contain the **full content so far**, not just the new delta. So if the agent first calls a tool and then writes text, the yielded content grows from `[tool-call]` to `[tool-call, text]`.

The adapter tracks:
- `currentText` — the assistant's accumulated text output
- `toolCalls` — an array of tool-call content parts, each with an id, name, args, and eventually a result
- `toolCallIndex` — a map from tool_call_id to its position in the array, so when a `tool_result` event arrives, the adapter can patch the result into the right tool-call part

### Loading message history

When the user selects a session, `useChatRuntime` fetches the full message history via `getMessages(sessionId)` and converts it to assistant-ui's format using `toThreadMessages()`.

The server stores messages flat:
```
assistant (tool_calls: [{id: "abc", name: "read_file", ...}])
tool      (tool_call_id: "abc", content: "file contents")
assistant (content: "Based on that file...")
```

`toThreadMessages` merges these into a single assistant turn:
```
assistant [tool-call("read_file", result="file contents"), text("Based on that file...")]
```

It does this by:
1. Building a lookup map of all tool results by `tool_call_id`.
2. Walking the message list. User messages become user turns. Consecutive assistant+tool messages get merged into one assistant turn with tool-call parts (including their results) and text parts.

### ChatPanel — putting it together

`ChatPanel` calls `useChatRuntime(sessionId)` to get the runtime, then wraps assistant-ui's `<Thread />` in an `<AssistantRuntimeProvider>`. It also registers tool UIs (see next section) so tool calls render visually instead of being hidden.

### If you want to extend this

- **Show typing indicators or status**: you can yield intermediate content in the adapter's `run()`. assistant-ui will re-render the thread on each yield.
- **Add message editing or regeneration**: assistant-ui supports these features — check their docs and wire them into the adapter.
- **Change how history displays**: modify `toThreadMessages` to alter how server messages map to thread messages.

---

## 4. Tool Call Rendering

**Files:** `components/tools/index.tsx`, `components/tools/ToolCallRenderer.tsx`

When the agent calls a tool (like `read_file` or `run_shell`), assistant-ui needs to know how to render it. By default, assistant-ui **hides** tool-call parts that don't have a registered UI. So you must register a UI for every tool you want visible.

### How registration works

`index.tsx` defines a `TOOL_NAMES` array listing every tool the server might produce:

```ts
const TOOL_NAMES = [
  "read_file", "write_file", "edit_file", "run_shell",
  "grep", "glob", "web_search", "web_extract",
  "get_weather", "spawn_agents",
];
```

For each name, it calls `makeAssistantToolUI()` to create a component that assistant-ui will use when it encounters that tool. All of them currently use the same generic `ToolCallRenderer`.

### ToolCallRenderer

A collapsible panel that shows:
- The tool name and a running/error status indicator
- When expanded: the JSON args and the JSON result

This is the fallback for all tools. It works for anything but isn't pretty for specific tools.

### If you want to extend this

- **Add a new tool the server can call**: add its name to the `TOOL_NAMES` array. That's it — the generic renderer handles the rest.
- **Build a custom renderer for a specific tool**: instead of using the generic renderer, create a dedicated component. For example, for `read_file` you might want syntax-highlighted code. Do this:

  ```ts
  // In components/tools/index.tsx or a new file
  const ReadFileToolUI = makeAssistantToolUI({
    toolName: "read_file",
    render: ({ args, result, status }) => (
      <YourCustomReadFileComponent args={args} result={result} status={status} />
    ),
  });
  ```

  Then replace the generic entry in `toolUIs` with this one, or build a system that checks for custom renderers before falling back to the generic one.

---

## Styling

**Files:** `src/index.css`

The app uses Tailwind CSS v4 with the `@tailwindcss/vite` plugin. There's no `tailwind.config.js` — Tailwind v4 uses CSS-based configuration.

`index.css` imports Tailwind, then imports assistant-ui's base styles and markdown styles. Below that, it overrides assistant-ui's CSS variables (prefixed `--aui-*`) to create a warm cream/brown theme. The chat thread uses Georgia (serif) as its font.

If you want to change colors or spacing in the chat area, look at the `--aui-*` variables and the `.aui-*` class overrides in `index.css`. For the sidebar, header, and other custom components, styling is inline via Tailwind classes.

---

## How to Run It

1. Start the FastAPI backend on port 8000 (see the server docs).
2. `npm install` then `npm run dev`. Vite starts on `localhost:5173` and proxies API calls to the backend.

---

## Summary of Where to Look

| I want to...                        | Look at                                      |
|-------------------------------------|----------------------------------------------|
| Change how sessions are created     | `NewSessionDialog`, `api/sessions.ts`        |
| Add a new API call                  | `api/client.ts` (use `apiFetch`)             |
| Handle a new SSE event type         | `types/message.ts`, `lib/sse.ts`, `use-chat-runtime.ts` |
| Change how messages render          | `index.css` (assistant-ui theme overrides)   |
| Add a new tool to the UI            | `components/tools/index.tsx` (add to `TOOL_NAMES`) |
| Build a custom tool renderer        | `components/tools/` (new component + `makeAssistantToolUI`) |
| Change the sidebar layout           | `components/layout/Sidebar.tsx`              |
| Change what the header shows        | `components/layout/Header.tsx`               |
| Modify how history loads            | `toThreadMessages` in `use-chat-runtime.ts`  |
