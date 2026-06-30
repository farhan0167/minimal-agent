"""Rich-based rendering for the terminal UI."""

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.rule import Rule
from rich.text import Text

from minimal_agent.llm.types import Message, Role, Usage

console = Console()


def print_header(model: str, backend: str, workspace: str) -> None:
    console.print()
    console.print("[bold green]minimal-agent[/bold green]")
    console.print(f"[dim]{model} · {backend}[/dim]")
    console.print(f"[dim]{workspace}[/dim]")
    console.print("[dim]/help for commands · Ctrl+D to exit[/dim]")
    console.print(Rule(style="dim"))


def print_user(content: str) -> None:
    console.print(f"[bold cyan]> {content}[/bold cyan]")
    console.print()


def print_assistant(content: str) -> None:
    md = Markdown(content)
    console.print(md)
    console.print()


def print_tool_call(name: str, arguments: dict) -> None:
    # Compact one-liner, dimmed
    args_str = ", ".join(f"{k}={v!r}" for k, v in arguments.items())
    console.print(f"  [dim]▶ {name}({args_str})[/dim]")


def print_tool_result(content: str | None) -> None:
    if not content:
        return
    # Show a truncated preview, dimmed
    preview = content[:200]
    if len(content) > 200:
        preview += "…"
    console.print(f"  [dim]  ↳ {preview}[/dim]")


def print_message(msg: Message) -> None:
    """Render a single (non-streamed) message from agent.run()."""
    if msg.role == Role.ASSISTANT:
        if msg.tool_calls:
            for tc in msg.tool_calls:
                print_tool_call(tc.name, tc.arguments)
        if msg.content:
            print_assistant(msg.content)
    elif msg.role == Role.TOOL:
        print_tool_result(msg.content if isinstance(msg.content, str) else None)


class AssistantStream:
    """Renders streamed assistant text live, then re-renders it as Markdown.

    Tokens are shown raw (no Markdown parsing) inside a `rich.Live` region as
    they arrive — no per-chunk re-parse, so no flicker. On `finish()` the Live
    region is cleared and the full text is re-printed once as formatted
    Markdown, so the final block "snaps" into rendered form.

    Usage:
        stream = AssistantStream()
        stream.add(chunk_text)   # called per StreamChunk
        stream.finish()          # called when the assistant Message commits
    """

    def __init__(self) -> None:
        self._text = ""
        # transient=True so stopping the Live clears the raw lines, leaving the
        # terminal ready for the formatted re-print.
        self._live = Live(console=console, transient=True, auto_refresh=False)
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    def add(self, delta: str) -> None:
        if not delta:
            return
        if not self._started:
            self._live.start()
            self._started = True
        self._text += delta
        self._live.update(Text(self._text), refresh=True)

    def finish(self) -> None:
        """Tear down the live region and re-print the text as Markdown.

        Idempotent: the buffer is cleared after printing, so a second call
        (e.g. a defensive finish after the loop) prints nothing.
        """
        if self._started:
            self._live.stop()
            self._started = False
        if self._text:
            print_assistant(self._text)
            self._text = ""


def print_usage(usage: Usage | None) -> None:
    if usage is None:
        console.print("[dim]No usage data yet.[/dim]")
        return
    console.print(
        f"[dim]Tokens — "
        f"prompt: {usage.prompt_tokens:,}  "
        f"completion: {usage.completion_tokens:,}  "
        f"total: {usage.total_tokens:,}[/dim]"
    )


def print_session_list(
    sessions: list, current_id: str | None = None
) -> None:
    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return

    for i, meta in enumerate(sessions[:10], 1):
        marker = " ←" if meta.session_id == current_id else ""
        tokens = f"{meta.usage.total_tokens:,} tokens" if meta.usage else "no usage"
        console.print(
            f"  [bold][{i}][/bold] {meta.session_id}  "
            f"[dim]({tokens}){marker}[/dim]"
        )
    console.print("  [bold]\\[n][/bold] New session")


def print_error(msg: str) -> None:
    console.print(f"[red]{msg}[/red]")


def print_info(msg: str) -> None:
    console.print(f"[dim]{msg}[/dim]")


def prompt_permission(tool_name: str, description: str) -> bool:
    """Ask the user for permission to run a tool. Returns True if allowed."""
    console.print(f"  [bold yellow]⚠ {description}[/bold yellow]")
    try:
        choice = console.input("  [bold]Allow? [y/N][/bold] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return choice in ("y", "yes")
