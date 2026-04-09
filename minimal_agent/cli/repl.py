"""The REPL loop: input → agent.run() → render."""

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner

from agent import Agent, Session
from llm.types import Message, Role

from . import render

console = Console()


def _build_prompt_session() -> PromptSession:
    """Build a prompt_toolkit session with multiline support.

    Enter submits. Shift+Enter or Alt+Enter inserts a newline.
    """
    bindings = KeyBindings()

    @bindings.add("escape", "enter")
    def _newline(event):
        event.current_buffer.insert_text("\n")

    return PromptSession(
        key_bindings=bindings,
        multiline=False,  # Enter submits by default
    )


async def run_loop(agent: Agent, session: Session) -> None:
    """Run the interactive REPL loop."""
    prompt_session = _build_prompt_session()

    while True:
        try:
            user_input = await prompt_session.prompt_async(
                HTML("<ansigreen><b>&gt; </b></ansigreen>"),
            )
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
            live = Live(
                Spinner("dots", text="[dim]Thinking…[/dim]"),
                console=console,
                transient=True,
            )
            live.start()
            first = True

            def _make_permission_callback(spinner: Live):
                async def _ask(tool_name: str, description: str) -> bool:
                    """Stop spinner, prompt user, restart spinner."""
                    was_started = spinner.is_started
                    if was_started:
                        spinner.stop()
                    allowed = render.prompt_permission(tool_name, description)
                    if was_started:
                        spinner.start()
                    return allowed

                return _ask

            _ask_permission = _make_permission_callback(live)

            async for msg in agent.run(
                session.context,
                on_usage=session.update_usage,
                permission_callback=_ask_permission,
            ):
                if first:
                    live.stop()
                    first = False
                render.print_message(msg)
                # Show spinner again while waiting for next LLM call
                if msg.role == Role.TOOL:
                    live.start()

            if live.is_started:
                live.stop()

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
        render.print_info("")
        render.print_info("Alt+Enter for multiline input.")

    else:
        render.print_error(f"Unknown command: {cmd}")

    return True
