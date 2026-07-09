# minimal-agent web

React + TypeScript chat frontend for [minimal-agent](../README.md). Built on
[`@assistant-ui/react`](https://www.assistant-ui.com/) with a custom
`LocalRuntime` adapter that streams agent responses over SSE from the FastAPI
backend.

## Quick start

```bash
npm install
npm run dev        # Vite dev server on http://localhost:5173
```

The dev server proxies `/api/*` to `http://localhost:8000` (stripping the
`/api` prefix), so the FastAPI backend must be running separately. In
production builds, set `VITE_API_BASE_URL` to the server's URL.

Other scripts:

```bash
npm run build      # tsc -b && vite build → dist/
npm run lint       # ESLint (TypeScript + React hooks rules)
npm run preview    # serve the production build locally
```

## Layout

| Path | What lives there |
|---|---|
| `src/api/` | HTTP + SSE client functions (`sendMessage` is an async generator over SSE events) |
| `src/lib/sse.ts` | Parses raw SSE streams into typed events: `delta`, `reasoning`, `assistant`, `tool_result`, `error`, `done` |
| `src/hooks/use-chat-runtime.ts` | The integration layer: converts server history to assistant-ui messages and adapts the SSE stream to `useLocalRuntime` |
| `src/components/chat/` | Thread, message, reasoning, and markdown/Shiki components |
| `src/components/markdown/` | Rich renderers for specific code fences — see below |
| `src/components/tools/` | **Tool call rendering** — see below |
| `src/types/` | TypeScript mirrors of the backend API schema |

Styling is Tailwind CSS v4 (CSS-based config in `src/index.css`, no
`tailwind.config`). Light/dark palettes are keyed off a `.dark` class on
`<html>`, toggled by `src/hooks/use-theme.ts`.

## Rich code fences

Assistant messages render markdown via `makeMarkdownText` (configured in
`src/components/chat/ChatPanel.tsx`). Its `componentsByLanguage` option maps
fence languages to custom renderers in `src/components/markdown/`:

- **`html`** — the code-block header gains a **Preview** button that opens
  the markup in a dialog with `<iframe sandbox="allow-scripts" srcDoc=…>`.
  Never add `allow-same-origin`: combined with `allow-scripts` it would let
  previewed content escape the sandbox and reach this origin.
- **`svg` / `xml`** — complete SVG documents render live, sanitized with
  DOMPurify (SVG profile, `foreignObject`/`script` forbidden, 256 KiB cap)
  inside a shadow root so their styles can't leak into the app. A toggle
  flips between rendered and source views; non-SVG XML falls through to
  normal highlighting.
- **`mermaid`** — diagrams render via a lazy-loaded mermaid import
  (`securityLevel: "strict"`, theme follows dark mode). While the message is
  still streaming a placeholder shows; invalid diagrams fall back to
  highlighted source.

To add a renderer for another fence language, build a component that accepts
assistant-ui's `SyntaxHighlighterProps` (or `CodeHeaderProps` to change only
the header) and register it in the `componentsByLanguage` map. Always keep a
fallback path to plain highlighted source — fences stream in incomplete.

## How tool calls render

When the agent calls a tool, the UI shows a collapsible card in the message
flow: tool name, a context subtitle (file path, command, query…), a status
badge, and an expandable body.

The moving parts, all under `src/components/tools/`:

1. **`index.tsx` — `buildToolUIs`.** On startup the app fetches tool names
   from `GET /tools` and registers an assistant-ui tool UI for each one.
   assistant-ui hides tool calls with no registered UI, so every tool gets
   one. It also maps assistant-ui's message status plus the result payload to
   our four-state `ToolStatus` (see below).
2. **`registry.ts` — `TOOL_RENDERERS`.** A plain `Record<string, FC<ToolRenderProps>>`
   mapping tool names to dedicated renderers. Tools not in the map fall back
   to the generic renderer.
3. **`ToolCallRenderer.tsx`** — the generic fallback: pretty-printed args
   JSON, the raw result (scroll-capped), and inline previews for any
   `data:image/...` URIs embedded in the result.
4. **`ToolCallCard.tsx`** — the shared collapsible shell plus body building
   blocks. Every renderer, dedicated or generic, composes this.

### What a renderer receives

```ts
interface ToolRenderProps {
  name: string;                     // tool name, e.g. "read_file"
  args: Record<string, unknown>;    // parsed tool arguments
  result: unknown;                  // tool result, undefined while running
  status: ToolStatus;               // "running" | "complete" | "error" | "interrupted"
}
```

Two contract details worth internalizing:

- **`result` is a string, formatted server-side.** Each backend tool's
  `render_result_for_assistant` (in
  `minimal_agent/src/minimal_agent/tools/builtin/<tool>/tool.py`) decides
  what the model — and therefore this UI — sees. A renderer that parses the
  result is coupled to that format, so link the backend file in a comment and
  **fail soft**: if parsing doesn't match, fall back to raw text rather than
  rendering garbage.
- **Failures are strings too.** The backend prefixes error results with one
  of `error:`, `invalid arguments:`, `validation failed:`, `permission
  error:`, `permission denied:`, `tool error:` (see
  `tools/dispatcher.py`). `buildToolUIs` detects these and hands your
  renderer `status === "error"` — you never need to sniff the prefix
  yourself.

Status semantics:

| `status` | Meaning | Renderer obligation |
|---|---|---|
| `running` | Call announced, no result yet | `args` are complete; `result` is `undefined` |
| `complete` | Finished successfully | Parse and render the result |
| `error` | Result carries an error string | Show it raw and red — don't parse it |
| `interrupted` | Turn was cancelled mid-call | Result may never arrive |

## Writing a renderer for a new tool

Say the backend grows a `get_weather` tool whose result renders as
`"72°F, partly cloudy in San Francisco"` with args `{ location: string }`.

**1. Know the contract.** Read the tool's `schema.py` (args) and
`render_result_for_assistant` (result string) under
`minimal_agent/src/minimal_agent/tools/builtin/get_weather/`.

**2. Create `src/components/tools/renderers/GetWeather.tsx`:**

```tsx
import { ToolCallCard, ResultSection } from "../ToolCallCard";
import type { ToolRenderProps } from "../types";

export function GetWeatherRenderer({ name, args, result, status }: ToolRenderProps) {
  const location = typeof args.location === "string" ? args.location : "";

  return (
    // subtitle = the one-line context a user wants without expanding the card
    <ToolCallCard name={name} status={status} subtitle={location}>
      {/* ResultSection handles the error + fallback cases for you:
          - status === "error" → raw result, red-tinted, children ignored
          - children undefined → raw result
          - otherwise → your rich rendering */}
      <ResultSection result={result} status={status}>
        {typeof result === "string" ? (
          <p className="text-sm p-3 rounded-lg bg-[hsl(var(--claude-hover))]">
            {result}
          </p>
        ) : undefined}
      </ResultSection>
    </ToolCallCard>
  );
}
```

**3. Register it in `registry.ts`:**

```ts
import { GetWeatherRenderer } from "./renderers/GetWeather";

export const TOOL_RENDERERS: Record<string, FC<ToolRenderProps>> = {
  // ...
  get_weather: GetWeatherRenderer,
};
```

Done — `buildToolUIs` picks it up automatically since tool names come from
the server. No other wiring.

### Building blocks

All exported from files in `src/components/tools/`:

| Component | Use for |
|---|---|
| `ToolCallCard` | The shell. Always the root of a renderer. `subtitle` is the collapsed-state context; keep it one line (it truncates). |
| `ResultSection` | The "Result" body section. Routes errors to a red raw block and un-parseable results to a plain raw block, so your custom rendering only ever sees success output. |
| `ArgsSection` | Pretty-printed args JSON, when raw args are genuinely useful (the generic renderer uses it). |
| `SectionLabel` | The small muted heading above a body section. |
| `RawResult` | Scroll-capped `<pre>` for raw text, with an `isError` red variant. |
| `CodeBlock` (`CodeBlock.tsx`) | Shiki-highlighted code, dual light/dark themes. Pair with `languageForPath()` from `src/lib/code-language.ts` to infer the language from a file path, or pass `"diff"` for diffs. |
| `ToolMarkdown` (`ToolMarkdown.tsx`) | Markdown rendering for prose-like results (the assistant's own markdown component is bound to message context and can't render arbitrary strings). |

### Rules of thumb

- **Render from `args` when you can.** Args arrive before the result, so a
  diff built from `old_string`/`new_string` (see `renderers/EditFile.tsx`) or
  file content from `write_file` args shows while the tool is still running.
- **Guard every field.** During streaming `args` can be empty and `result`
  `undefined`; type-check (`typeof args.x === "string"`) instead of casting.
- **Cap the height.** Results can be huge — use `max-h-*` + `overflow-y-auto`
  on anything unbounded (the building blocks above already do).
- **Parsing fails soft.** Return `null`/`undefined` from your parser on
  format mismatch and let `ResultSection` show the raw text. A renderer must
  never be the reason a result is invisible.
- **Existing renderers are the reference.** `renderers/ReadFile.tsx` (parse +
  highlight), `renderers/RunShell.tsx` (terminal styling),
  `renderers/WebSearch.tsx` (structured parse with fallback) cover the three
  common shapes.
