"""The REPL loop: input → agent.run() → render."""

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner

from minimal_agent.agent import Agent, Session
from minimal_agent.llm.types import Message, Role, StreamChunk

import render

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
            spinner = Live(
                Spinner("dots", text="[dim]Thinking…[/dim]"),
                console=console,
                transient=True,
            )
            spinner.start()
            stream = render.AssistantStream()

            def _make_permission_callback():
                async def _ask(tool_name: str, description: str) -> bool:
                    """Pause whichever live region is active, prompt, resume."""
                    was_spinning = spinner.is_started
                    if was_spinning:
                        spinner.stop()
                    allowed = render.prompt_permission(tool_name, description)
                    if was_spinning:
                        spinner.start()
                    return allowed

                return _ask

            _ask_permission = _make_permission_callback()

            async for item in agent.run(
                session.context,
                stream=True,
                on_usage=session.update_usage,
                permission_callback=_ask_permission,
            ):
                if isinstance(item, StreamChunk):
                    # First token of the turn: hand the terminal off from the
                    # thinking spinner to the live text region.
                    if item.text and spinner.is_started:
                        spinner.stop()
                    stream.add(item.text)
                    continue

                # item is a committed Message.
                if item.role == Role.ASSISTANT:
                    # Snap the streamed raw text into formatted Markdown, then
                    # render any tool-call lines (only known at commit time).
                    stream.finish()
                    if item.tool_calls:
                        for tc in item.tool_calls:
                            render.print_tool_call(tc.name, tc.arguments)
                elif item.role == Role.TOOL:
                    render.print_message(item)
                    # Wait on the next LLM call with the spinner up again.
                    spinner.start()

            if spinner.is_started:
                spinner.stop()
            stream.finish()

        except KeyboardInterrupt:
            render.print_info("\n[interrupted]")
            if spinner.is_started:
                spinner.stop()
            stream.finish()
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
