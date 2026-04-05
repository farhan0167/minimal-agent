---
name: explain
description: Explain code the user is looking at (IDE selection or opened file) or a concept in the codebase. Use when the user asks "explain this", "what does this do", "walk me through X", "how does Y work here", or similar — especially when an IDE selection or opened file is present in context.
---

# Explain

Explain something for the user. The "something" is one of two modes — figure out which before doing anything else.

## Step 1: Read the user's request

The user's message is the steering note. It may be terse ("explain this", "eli5") or specific ("how does async tool-call streaming work?", "why is config loaded this way?").

Use the request to decide which mode you're in:

- **Mode A — Explain current code.** The user wants a walkthrough of a specific chunk of code. This is the default when the request is about *this* code ("explain this", "eli5", "focus on error handling", "walk me through it", "just these lines", "what does the highlighted block do?"). If the request explicitly points at the selection ("these lines", "the highlighted block", "this snippet"), treat the IDE selection as authoritative even if an opened file is also present — explain only the selected lines. If no lines are selected, fall back to the whole opened file and mention that you're doing so.
- **Mode B — Explain a concept.** The user is asking a question about an idea, mechanism, or decision in the codebase ("how does X work here?", "why is Y done this way?", "where does Z happen?"). The relevant code has to be *found* before it can be explained.

If the request is ambiguous, pick the mode that best serves the question and say which one you picked in one line at the top of your answer.

## Step 2: Find the target

**In Mode A (current code):**
1. **Scan the conversation context for an `<ide_selection>` tag.** It contains lines like "The user selected the lines X to Y from /absolute/path" followed by the selected code. If present, the selection is the target — explain only those lines, and cite them using the file path and line range from the tag. Do NOT skip this step or assume there is no selection; actually look for the tag.
2. Otherwise, scan for an `<ide_opened_file>` tag — if present, read and explain that whole file.
3. Only if **neither** tag is present should you ask the user what to explain. Never ask the user "what do you want me to explain?" while an `<ide_selection>` or `<ide_opened_file>` tag is sitting in the context.

**In Mode B (concept):**
1. Search the repo for the concept the user is asking about (Grep/Glob, or the Explore agent for broader questions). The opened file and selection are hints about where the user is looking, but don't limit the search to them.
2. Read the relevant files in full before answering. Don't explain a mechanism from a single grep hit.
3. Cite the specific files and lines that implement the concept.

## Step 3: Answer

**In Mode A**, if the request specifies a shape (audience, depth, focus, format), follow it and skip the default structure. Otherwise cover:
- **Purpose**: what this code does and why it exists in the broader codebase.
- **Key mechanics**: how it works — walk through non-obvious logic, control flow, and tricky details.
- **Inputs/outputs**: what it takes in, what it returns, and any side effects.
- **Context**: how it connects to surrounding modules or callers.
- **Gotchas**: edge cases, caveats, or things a reader might miss.

**In Mode B**, answer the user's question directly. Structure the answer around the concept, not around files — but anchor every claim to the code you found. A good concept explanation reads like "here's how X works: [mechanism], implemented in [file:line]. The tricky part is [Y], which is handled at [file:line]."

## Formatting

Use file:line references in markdown link format (e.g. `[llm.py:42](llm/llm.py#L42)`) when citing specific lines. Be concise — skip trivial details and focus on what the user actually needs to understand.
