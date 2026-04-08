"""CLI entrypoint: setup agent, session picker, run REPL."""

from pathlib import Path

from agent import Agent, Session
from config import settings
from llm import LLM
from tools.builtin.get_weather import GetWeather
from tools.builtin.glob import Glob
from tools.builtin.grep import Grep
from tools.builtin.read_file import ReadFile
from tools.builtin.run_shell import RunShell
from tools.builtin.write_file import WriteFile

from . import render
from .repl import run_loop


def _build_agent(workspace: Path) -> Agent:
    """Construct the default agent with all builtin tools."""
    llm = LLM(
        model=settings.LLM_MODEL,
        backend=settings.LLM_BACKEND,
        timeout=settings.OPENAI_TIMEOUT,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )

    read_timestamps: dict[str, float] = {}

    return Agent(
        llm=llm,
        tools=[
            GetWeather(),
            ReadFile(
                workspace_root=workspace,
                read_timestamps=read_timestamps,
            ),
            WriteFile(
                workspace_root=workspace,
                read_timestamps=read_timestamps,
            ),
            RunShell(workspace_root=workspace),
            Grep(workspace_root=workspace),
            Glob(workspace_root=workspace),
        ],
    )


async def _pick_session(system_prompt: str) -> Session | None:
    """Let the user pick an existing session or create a new one."""
    sessions_dir = Path(settings.SESSIONS_DIR)
    sessions = Session.list_sessions(base_dir=sessions_dir)

    if not sessions:
        render.print_info("Starting new session.")
        return Session.create(
            model=settings.LLM_MODEL,
            backend=settings.LLM_BACKEND,
            system_prompt=system_prompt,
            base_dir=sessions_dir,
        )

    render.print_session_list(sessions)
    render.console.print()

    while True:
        try:
            choice = render.console.input(
                "[bold]Choose a session[/bold] [dim](number or 'n' for new)[/dim]: "
            )
        except (EOFError, KeyboardInterrupt):
            render.print_info("\nStarting new session.")
            return Session.create(
                model=settings.LLM_MODEL,
                backend=settings.LLM_BACKEND,
                system_prompt=system_prompt,
                base_dir=sessions_dir,
            )

        choice = choice.strip().lower()

        if choice in ("/exit", "/quit", "/q"):
            return None

        if choice == "n" or choice == "":
            return Session.create(
                model=settings.LLM_MODEL,
                backend=settings.LLM_BACKEND,
                system_prompt=system_prompt,
                base_dir=sessions_dir,
            )

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(sessions[:10]):
                meta = sessions[idx]
                return Session.load(
                    session_id=meta.session_id,
                    model=settings.LLM_MODEL,
                    backend=settings.LLM_BACKEND,
                    system_prompt=system_prompt,
                    base_dir=sessions_dir,
                )
        except ValueError:
            pass

        render.print_error("Invalid choice. Enter a number or 'n'.")


async def run() -> None:
    """Main entrypoint for the CLI."""
    workspace = Path.cwd()
    agent = _build_agent(workspace)

    render.print_header(
        model=settings.LLM_MODEL,
        backend=settings.LLM_BACKEND,
        workspace=str(workspace),
    )

    system_prompt = await agent.build_system_prompt(workspace_root=workspace)
    session = await _pick_session(system_prompt)

    if session is None:
        render.print_info("Goodbye.")
        return

    render.print_info(f"Session: {session.session_id}")
    render.print_info("")

    await run_loop(agent, session)
