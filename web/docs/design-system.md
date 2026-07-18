# The design system

How the frontend is styled, and how to extend it without a redesign. Read this
before you add a color class, write a theme, or build a new UI component.

The short version: **four floors, each reaching only one floor down.** A feature
composes primitives. A primitive is the only place raw Tailwind touches tokens.
A token names a *role*, never a value. A theme fills every token, for light and
dark. That single "reach one floor down" constraint is the whole reason a new
theme is one file instead of a twenty-file diff.

```
features        components/chat · session · layout · tools
  │  composition only — zero color/shape/font classes
  ▼
primitives      components/ui/
  │  the only home of raw Tailwind utilities; references tokens, never values
  ▼
tokens          tokens.css (contract) + index.css (@theme bridge)
  │  roles, not values — --app-hover, --app-radius-bubble, --app-font-prose
  ▼
themes          themes/*.css (values) + themes/*.ts (manifest)
```

The rule for each boundary:

| Floor | May contain | May **not** contain |
|-------|-------------|---------------------|
| features | primitives, props, layout classes (`flex`, `gap-2`, `w-full`) | any `bg-*`/`text-*`/`rounded-*` color or shape class; any font family; any hex |
| primitives (`components/ui/`) | raw Tailwind utilities that read tokens (`bg-app-hover`, `rounded-ctl`) | literal hex, literal radii, `font-serif`, Tailwind palette classes (`bg-zinc-900`) |
| tokens | role names and the `@theme` bridge that exposes them | values — this floor is deliberately value-free |
| themes | the actual values, for both modes | nothing above it knows a theme exists |

A CI guard (`npm run check:tokens`) enforces the top two rows by grep. See
[The floor guard](#the-floor-guard) below.

---

## Where everything lives

```
src/
  tokens.css              the contract: every --app-* role, with no values (documentation)
  index.css               the @theme bridge (roles → Tailwind utilities) + the chat chrome
  components/ui/          the ten primitives — the only floor allowed raw utilities
  themes/
    types.ts              ThemeManifest — what a theme must declare beyond CSS
    index.ts              the registry; import a theme's css + manifest here to register it
    claude.css            values for the claude theme, light + dark
    claude.ts             claude's manifest (Shiki + Mermaid companions)
    blueprint.css         values for blueprint (the technical-minimal theme)
    blueprint.ts          blueprint's manifest
  hooks/
    use-theme.ts          owns {theme, mode}; stamps <html>; persists both
    use-theme-tokens.ts   reads {theme, mode} from the DOM, for consumers that can't read --app-*
  scripts/check-tokens.mjs  the floor guard (npm run check:tokens)
```

Two axes are always independent: **identity** (`data-theme="claude"`) and
**mode** (`class="dark"`). Both are stamped on `<html>`. Switching theme never
resets your light/dark choice, and vice versa.

```html
<html data-theme="blueprint" class="dark">
```

---

## The token contract

A token names what a thing is *for* — `--app-hover`, `--app-radius-bubble`,
`--app-font-prose` — never what it looks like. That is the load-bearing idea:
because roles don't encode a look, a second theme answers the same questions
with different values and nothing above the themes floor changes.

`tokens.css` lists every role in one place and holds **no values on purpose**. A
theme that misses a token leaves the app unstyled at that role — which is louder
and easier to fix than silently inheriting a look nobody chose. Read `tokens.css`
for the authoritative, commented list; the groups are:

| Group | Answers |
|-------|---------|
| **Ground** | page, text, muted text, surface, sidebar, composer backgrounds |
| **Interaction** | hover, active, border, subtle border, focus ring |
| **Accent & semantic** | accent + its foreground/hover/text, danger, success, warning |
| **Chat** | user bubble, modal overlay, shadow, empty-state canvas texture |
| **Code** | code block bg/header/button, inline code bg/fg |
| **Terminal** | the RunShell palette (bg, fg, muted, dim, accent, border) |
| **Typography** | ui/prose/mono font, prose weight, markdown heading sizes; the micro-label voice (label font + case + tracking) |
| **Shape** | control/badge/bubble/composer/surface radii |
| **Motion** | one transition (duration + easing) |

### Two conventions that trip people up

**Color tokens are bare HSL triplets**, not full colors:

```css
--app-bg: 40 20% 96%;        /* not hsl(40 20% 96%) */
```

so a call site can compose alpha: `hsl(var(--app-bg) / 0.5)`. The bridge wraps
them in `hsl()` for you, so components just write `bg-app-bg`.

**Alpha-bearing tokens are the exception** — `--app-border`, `--app-hover`,
`--app-active`, `--app-overlay` carry their own opacity because their whole job
is to tint whatever they sit on:

```css
--app-hover: 0 0% 0% / 0.06;
```

One consequence worth knowing: a translucent token tints its host but does not
*paint* a ground. `--app-border-opaque` exists for the one consumer that needs
the same edge pre-flattened into a solid fill (Switch's off-state track — a
translucent track would show the row through it).

### The bridge (`index.css`)

`@theme inline` maps each `--app-*` role onto a Tailwind namespace, so call
sites read `bg-app-hover rounded-ctl font-prose` instead of the
`bg-[hsl(var(--app-hover))]` arbitrary-value spelling:

```css
@theme inline {
  --color-app-hover: hsl(var(--app-hover));
  --radius-ctl:      var(--app-radius-ctl);
  --font-prose:      var(--app-font-prose);
  /* …one line per token… */
}
```

`inline` matters: it resolves the `var()` at the use site rather than copying
the value, so a theme's `.dark` overrides still win.

Motion is the one role a Tailwind slot can't hold (`"140ms ease"` is a duration
*and* an easing), so it ships as a `@utility transition-app` that primitives
apply by name — replacing the old per-file coin-flip between `transition-colors`
and `transition-opacity`.

**When you add a new role**, you touch three files: name it in `tokens.css`, add
its bridge line in `index.css`, and fill it in *every* theme CSS. Skipping the
last is what the "unstyled at that role" design is meant to make obvious.

---

## Writing a new theme

A theme is **one CSS file + one manifest + one registry line**. Nothing above
the themes floor changes. Concretely, to add a theme called `midnight`:

### 1. `themes/midnight.css` — fill the contract, both modes

Copy `claude.css` as the skeleton (it fills every token and is the reference for
the alpha-vs-triplet split). The selector is the identity axis; `.dark` layers
the mode on top:

```css
[data-theme="midnight"] {
  --app-bg: 220 26% 14%;
  --app-fg: 210 20% 92%;
  /* …every token in tokens.css… */
  --app-accent: 213 94% 68%;
  --app-accent-fg: 220 26% 14%;   /* text ON the accent */
  --app-font-prose: Georgia, serif;
  --app-radius-bubble: 1rem;
  /* …etc… */
}

[data-theme="midnight"].dark {
  /* only the tokens that differ in dark; the rest inherit the block above */
  --app-bg: 220 30% 8%;
  --app-fg: 210 20% 96%;
}
```

**`--app-accent-fg` is not decoration.** A theme with a light accent (blueprint's
near-white button in dark mode) needs *dark* text on it. That token is the whole
reason a button stays legible when the accent inverts. If you skip it, a light
accent gets light text and vanishes.

### 2. `themes/midnight.ts` — the manifest

The parts a stylesheet can't reach. Shiki compiles a named theme into inline
styles and Mermaid draws to SVG, so neither can read `--app-*`; the theme names
its companions here instead of hardcoding them in the renderers:

```ts
import type { ThemeManifest } from "./types";

export const midnight: ThemeManifest = {
  id: "midnight",             // must match the data-theme selector in the css
  name: "Midnight",           // shown in the theme picker
  shiki:   { light: "github-light-default", dark: "github-dark-default" },
  mermaid: { light: "neutral", dark: "dark" },
};
```

`ShikiThemes.light/dark` are Shiki bundle names (strings). `MermaidTheme` is a
closed union mirroring Mermaid's own — a typo there would silently render a
diagram in the wrong palette, so it's typed, not widened to `string`.

### 3. `themes/index.ts` — register it

Import the css and the manifest, add one entry to `THEMES`:

```ts
import { midnight } from "./midnight";
import "./midnight.css";

export const THEMES: Record<string, ThemeManifest> = {
  [claude.id]: claude,
  [blueprint.id]: blueprint,
  [midnight.id]: midnight,
};
```

The css is imported *here*, beside the manifest, so a theme is never
half-registered — the file that names it is the file that loads it.

### 4. Verify

Run `npm run check:tokens && npm run build`. Then flip to the theme in both
light and dark and look for anything that didn't change — an un-themed corner is
a leaked literal or a token your css missed. Treat your new theme as its own
acceptance test.

That's the entire change. You did not open a single file in `components/`.

---

## Writing a new primitive

Primitives live in `components/ui/` and are the **only** floor allowed to write
raw Tailwind utilities. A primitive decides what a thing *is* — its padding,
radius, hover treatment, transition, and focus ring — once, so no feature file
ever re-decides it.

Rules for a primitive:

- **Read tokens, never values.** `bg-app-surface rounded-surface`, not
  `bg-[#fff] rounded-[0.5rem]` and not `bg-zinc-100`. The guard enforces this
  everywhere *except* `components/ui/` — but the whole point is that
  `components/ui/` still only names roles; the exemption is for the bridge
  syntax, not for hardcoding a look.
- **Own the focus ring.** `focus-visible:ring-2 focus-visible:ring-app-ring`.
  Accessibility that lives in the primitive can't be forgotten at a call site.
- **Own the transition** with `transition-app`, not a hand-picked
  `transition-colors`.
- **Variants are props, not new components.** `Button` takes
  `variant="primary | ghost | icon | danger"`; a `size` axis is a prop too.
- **`className` is layout-only.** A caller may pass `className="w-full"` to
  place a primitive, but never `className="text-red-500"` to recolor it — if a
  feature needs a new look, that's a missing variant, and the fix goes into the
  primitive.
- **Carry the "why" in a header comment.** Every primitive opens with a short
  note on what it absorbs and which decision it centralizes. Match that.

Study `Text.tsx` (the typography roles), `Button.tsx` (variant + size + focus
ring), and `Field.tsx`/`Switch.tsx` (form controls with `useId` wiring) as the
reference shapes.

### Two lessons the existing primitives already paid for

**A label needs a color role, not an ambient one.** `Text variant="label"`
carries `text-app-fg`. A raw `<span>` for a label inherits whatever color
surrounds it and goes dark-on-dark the moment the mode flips. If your primitive
renders text, route it through `Text` (or apply a text role yourself) — never
leave a bare colorless span.

**Native controls can't read our classes.** A `<select>`'s native chevron and a
`<option>` popup are OS-drawn; no Tailwind class reaches them. `Select` resets
`appearance: none` and draws its own chevron, and `index.css` sets
`color`/`background-color` directly on `select option` (the only two properties
those popups honor). If you wrap a native control, expect to escape its chrome
this way.

---

## The chat chrome

The chat is built directly on `@assistant-ui/react` **primitives**
(`ThreadPrimitive`, `ComposerPrimitive`, `MessagePrimitive`, …), which render
their own elements — the thread viewport, the composer form and textarea,
markdown output. There is no vendor CSS in the app and no `--aui-*` second
palette; themes fill only the `--app-*` contract.

Because those primitive-rendered elements can't be wrapped in a
`components/ui/` primitive, their look lives in `index.css` under the
**chat chrome** section, on class names *we* own (`.chat-thread`,
`.chat-composer`, `.chat-user-bubble`, `.chat-prose`, `.chat-code-header`),
assigned by `components/chat/` and reading the same `--app-*` roles a
primitive would. Same contract, different consumer — and since the class names
are first-party, nothing there pins a package version.

`.chat-prose` is the markdown rhythm: `MarkdownText` renders bare elements
(`p`, `h1`, `ul`, `pre`, …) inside a `.chat-prose` container, and the chrome
block styles them by element selector. `ToolMarkdown` reuses the same class
for tool-result markdown, so thread prose and card prose can't drift apart.

---

## The floor guard

`npm run check:tokens` (also part of `npm run build` via CI) greps `src/` and
fails on:

| Rule | Catches | Fix |
|------|---------|-----|
| `raw-hex` | `#ae5630` | add a token to `tokens.css`, read it via the bridge |
| `tailwind-palette` | `bg-zinc-900` | use an `--app-*` role (`bg-app-surface`) |
| `arbitrary-token` | `bg-[hsl(var(--x))]` | the bridge means you can write `bg-app-*` |
| `font-literal` | `font-serif` | prose voice is `--app-font-prose` (`font-prose`) |

Exempt paths — the floors allowed to speak in literals — are `components/ui/`,
`themes/`, `tokens.css`, and `index.css`. Comments are stripped before scanning,
so an issue reference like `#185` in a comment won't trip `raw-hex`.

If the guard fires outside those paths, it's telling you a decision leaked up a
floor. Push it back down: a color → a token; a repeated widget → a primitive or
a new variant.

---

## History

This system replaced a flat set of ~15 `--claude-*` color-only variables, with
serif, radii, and weights hardcoded across components. The full rationale and
the six-step rollout that built it live in the design blueprint that supersedes
`docs/theming.md`. This document is the maintainer's guide to the result.
