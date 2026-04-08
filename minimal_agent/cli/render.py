"""Rich-based rendering for the terminal UI."""

from rich.console import Console
from rich.markdown import Markdown
from rich.rule import Rule

from llm.types import Message, Role, Usage

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
    """Render a single message from agent.run()."""
    if msg.role == Role.ASSISTANT:
        if msg.tool_calls:
            for tc in msg.tool_calls:
                print_tool_call(tc.name, tc.arguments)
        if msg.content:
            print_assistant(msg.content)
    elif msg.role == Role.TOOL:
        print_tool_result(msg.content if isinstance(msg.content, str) else None)


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
