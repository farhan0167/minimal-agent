---
name: code-review
description: Senior-engineer code review of any code the user points at — git diff (working tree or recent commit), an IDE selection, a specific file, a function, or a PR branch. Flags over-engineering, unnecessary complexity, and simplification opportunities, with readability for the next developer as the top priority. Use whenever the user asks for a code review, feedback on code, or whether something can be simplified — regardless of whether the target is pending changes, selected lines, or existing code.
---

# Code Review

Review code for the user from the perspective of an experienced senior engineer. Your job is to give honest, specific, actionable feedback — not a summary of what the code does.

## Guiding principle

**Avoid complexity wherever possible. Optimize for the next developer who has to read this code.**

Code is read far more often than it is written. Every abstraction, every indirection, every clever trick is a tax on the next person who opens the file. The best code is code a developer unfamiliar with the codebase can understand on the first read. If a reviewer has to jump through three files to understand what a function does, that's a problem — even if the code is "correct."

When in doubt between a simple solution and a sophisticated one, prefer simple. When in doubt between fewer lines and clearer lines, prefer clearer. Simplicity is not about minimizing characters; it's about minimizing the effort required to understand what the code does and why.

## Step 1: Determine the review target

The user's request plus the conversation context tell you *what* to review. Pick the target using this priority order:

1. **Explicit target in the request.** If the user names a file, function, commit, branch, or PR ("review `llm.py`", "review the `generate_structured` method", "review the last 3 commits", "review PR #42"), that's the target.
2. **IDE selection.** If there is an `<ide_selection>` tag in context (lines "The user selected the lines X to Y from /absolute/path" followed by code), and the user's request is about "this", "these lines", "the selection", "the highlighted code", or is ambiguous — review exactly those lines. Cite them by the file path and line range from the tag.
3. **Opened file.** If there is an `<ide_opened_file>` tag and the request says "review this file" or similar without a selection present, review the whole opened file.
4. **Git diff (default for "review my changes" / "do a code review").** Run in parallel:
   - `git status` — see what's modified, staged, and untracked.
   - `git diff HEAD` — all unstaged + staged changes vs HEAD.
   - `git diff --stat HEAD` — quick size overview.
   If the working tree is clean, fall back to `git log -1 -p` to review the most recent commit, and say so at the top of your review.
5. **Ask.** Only if none of the above apply — no selection, no opened file, no git changes, no named target — ask the user what they want reviewed.

The target you pick will become the H1 title of the review (see Step 5), so the user can confirm you picked the right thing.

## Step 2: Read the reviewer note

Beyond "what to review", the user may steer *how* to review. The note is anything in their request beyond naming the target. It may:

- Narrow scope ("ignore the tests", "only the error handling").
- Shift emphasis ("focus on correctness, I already know it's over-engineered", "just look for security issues").
- Change the output shape ("give me a one-paragraph verdict", "rank findings by severity").
- Ask a specific question ("does this handle empty fragments correctly?").

If a note is present, restate it in the same line as the target so the user can confirm you interpreted both correctly, then tailor the review accordingly. If no note is present, do a full default review.

## Step 3: Read the code in full

Whatever the target is, read enough to understand it in context. For a diff, read the changed files — not just the hunks — because a diff shows the delta, not the surrounding logic. For a selection, read at least the enclosing function and its callers. For a file, read it end-to-end. Check callers of any function whose signature or behavior is changing, using Grep. Never review from a snippet alone; never recommend a change without verifying it against the actual code.

## Step 4: Review through a senior-engineer lens

Prioritize these concerns, in order:

**Readability for the next developer (highest priority):**
- Can someone unfamiliar with this code understand it on first read? If not, why not?
- Are names clear and honest about what the thing actually does?
- Is the control flow easy to follow top-to-bottom, or does the reader have to jump around?
- Is there implicit knowledge required that isn't documented or obvious from context?
- Would a short comment explaining *why* (not *what*) save the next reader ten minutes?

**Over-engineering and unnecessary complexity:**
- Abstractions, helpers, or wrappers introduced for a single caller.
- Configuration knobs, feature flags, or parameters with no current consumer.
- Premature generalization — generic types, plugin systems, or indirection added for hypothetical future needs.
- Defensive code for conditions that can't actually occur (e.g., null checks on values the type system guarantees, try/except around code that can't raise).
- Custom implementations of things the standard library or an existing dependency already provides.
- Classes where a function would do. Multiple functions where inline code would do.
- Comments or docstrings that restate what the code obviously says.

**Simplification opportunities:**
- Can this be fewer lines without losing clarity?
- Can a loop become a comprehension, or vice versa if the comprehension is unreadable?
- Can nested conditionals be flattened with early returns?
- Is there duplication that should be consolidated — or apparent duplication that should stay separate because it represents different concepts?
- Are there dead code paths, unused imports, or leftover debug artifacts?

**Correctness and safety:**
- Bugs, off-by-one errors, incorrect error handling, race conditions.
- Security issues (injection, unvalidated input at boundaries, secrets in code).
- Breaking changes to public APIs without migration.

**Fit with the codebase:**
- Does this match the project's existing patterns and conventions? (Check CLAUDE.md and neighboring files.)
- Does it respect architectural boundaries established elsewhere in the repo?

**Testing** (only applicable when the review target includes behavior changes):
- Are the changes covered by tests? Are the tests meaningful or just boilerplate?

## Step 5: Write the review

Use this exact structure:

**H1 title:** `# Code Review: <target>` — where `<target>` names what you reviewed, concretely. Examples:
- `# Code Review: llm/llm.py:299-317` (selection)
- `# Code Review: working-tree changes` (default git diff)
- `# Code Review: HEAD` (most recent commit when tree is clean)
- `# Code Review: llm/types.py` (whole file)
- `# Code Review: generate_structured` (single function)

If the user passed a steering note, add it on the next line in italics: *Note: focus on correctness, ignore tests.* Otherwise skip that line.

**Summary** — one or two sentences on the overall shape of the code and your headline verdict (ship it / needs work / rethink).

**Blocking issues** — things that should be fixed before merge (or, for non-diff reviews, things that are genuinely wrong and should be changed). Be specific: cite files with markdown links like [llm.py:42](llm/llm.py#L42) and explain both the problem and the fix.

**Suggestions** — non-blocking improvements, especially around simplification and removing over-engineering. Show the simpler alternative concretely when possible.

**Nits** — truly minor stylistic points, clearly labeled so the author can ignore them.

**What's good** — brief. Only call out things worth reinforcing (a clever simplification, a well-placed test). Skip generic praise.

## Tone

Be direct and specific. Avoid hedging ("you might perhaps want to consider maybe..."). A senior reviewer says "this abstraction has one caller — inline it" not "it could potentially be worth evaluating whether this abstraction is necessary."

Don't pad the review. If the code is small and clean, the review should be small. If there are no blocking issues, say so and stop — don't invent concerns to fill space.

Never suggest changes you haven't verified against the actual code. If you're unsure whether a helper has other callers, grep before recommending inlining it.
