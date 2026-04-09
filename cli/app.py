"""CLI entrypoint: setup agent, session picker, run REPL."""

from pathlib import Path

from minimal_agent.agent import Agent, Session
from minimal_agent.config import settings
from minimal_agent.llm import LLM
from minimal_agent.tools.builtin.edit_file import EditFile
from minimal_agent.tools.builtin.get_weather import GetWeather
from minimal_agent.tools.builtin.glob import Glob
from minimal_agent.tools.builtin.grep import Grep
from minimal_agent.tools.builtin.read_file import ReadFile
from minimal_agent.tools.builtin.run_shell import RunShell
from minimal_agent.tools.builtin.spawn_agents import SpawnAgents
from minimal_agent.tools.builtin.web_extract import WebExtract
from minimal_agent.tools.builtin.web_search import WebSearch
from minimal_agent.tools.builtin.write_file import WriteFile

import render
from repl import run_loop


def _build_agent(workspace: Path) -> Agent:
    """Construct the default agent with all builtin tools."""
    llm = LLM(
        model=settings.LLM_MODEL,
        backend=settings.LLM_BACKEND,
        timeout=settings.OPENAI_TIMEOUT,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )

    read_timestamps: dict[str, float] = {}

    builtin_tools = [
        GetWeather(),
        ReadFile(
            workspace_root=workspace,
            read_timestamps=read_timestamps,
        ),
        EditFile(
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
        WebSearch(),
        WebExtract(),
    ]

    # Build a name→tool map so SpawnAgents can resolve sub-agent tool sets.
    tools_by_name = {t.name: t for t in builtin_tools}

    spawn_agents = SpawnAgents(
        llm=llm,
        available_tools=tools_by_name,
        workspace_root=workspace,
    )

    return Agent(
        llm=llm,
        tools=[*builtin_tools, spawn_agents],
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
