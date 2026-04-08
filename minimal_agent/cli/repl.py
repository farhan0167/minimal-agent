"""The REPL loop: input → agent.run() → render."""

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner

from agent import Agent, Session
from llm.types import Message, Role

from . import render

console = Console()


async def run_loop(agent: Agent, session: Session) -> None:
    """Run the interactive REPL loop."""
    while True:
        try:
            user_input = console.input("[bold green]> [/bold green]")
        except (EOFError, KeyboardInterrupt):
            render.print_info("\nGoodbye.")
            return

        user_input = user_input.strip()
        if not user_input:
            continue

        # Handle slash commands
        if user_input.startswith("/"):
            should_continue = _handle_command(user_input, session)
            if not should_continue:
                return
            continue

        # Send to agent
        session.context.add(Message(role=Role.USER, content=user_input))

        try:
            with Live(
                Spinner("dots", text="[dim]Thinking…[/dim]"),
                console=console,
                transient=True,
            ):
                # Collect all messages first (no streaming yet)
                messages: list[Message] = []
                async for msg in agent.run(
                    session.context, on_usage=session.update_usage
                ):
                    messages.append(msg)

            # Render after spinner clears
            for msg in messages:
                render.print_message(msg)

        except KeyboardInterrupt:
            render.print_info("\n[interrupted]")
            continue


def _handle_command(command: str, session: Session) -> bool:
    """Handle a slash command. Returns False if the REPL should exit."""
    cmd = command.lower().split()[0]

    if cmd in ("/exit", "/quit", "/q"):
        render.print_info("Goodbye.")
        return False

    elif cmd == "/usage":
        render.print_usage(session.usage)

    elif cmd == "/session":
        render.print_info(f"Session: {session.session_id}")
        render.print_info(f"Created: {session.created_at}")
        render.print_usage(session.usage)

    elif cmd == "/help":
        render.print_info("Commands:")
        render.print_info("  /help     — show this message")
        render.print_info("  /usage    — show token usage")
        render.print_info("  /session  — show session info")
        render.print_info("  /exit     — exit the REPL")

    else:
        render.print_error(f"Unknown command: {cmd}")

    return True
