"""CLI entrypoint: setup agent, session picker, run REPL."""

from pathlib import Path

from minimal_agent import LLM, Agent, Session, SessionManager, settings
from minimal_agent.agent import SessionConfigMismatchError
from minimal_agent.tools.builtin import (
    EditFile,
    Glob,
    Grep,
    ReadFile,
    RunShell,
    SpawnAgents,
    WebExtract,
    WebSearch,
    WriteFile,
)

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
        workspace_root=workspace,
        session_manager=SessionManager(base_dir=Path(settings.SESSIONS_DIR)),
    )


async def _pick_session(agent: Agent) -> Session | None:
    """Let the user pick an existing session or create a new one.

    Sessions are created and resumed through the agent's factories, so
    they always carry the agent's identity (system prompt, settings,
    persisted workspace).
    """
    sessions = agent.sessions.list_sessions()

    if not sessions:
        render.print_info("Starting new session.")
        return await agent.create_session()

    render.print_session_list(sessions)
    render.console.print()

    while True:
        try:
            choice = render.console.input(
                "[bold]Choose a session[/bold] [dim](number or 'n' for new)[/dim]: "
            )
        except (EOFError, KeyboardInterrupt):
            render.print_info("\nStarting new session.")
            return await agent.create_session()

        choice = choice.strip().lower()

        if choice in ("/exit", "/quit", "/q"):
            return None

        if choice == "n" or choice == "":
            return await agent.create_session()

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(sessions[:10]):
                meta = sessions[idx]
                try:
                    return await agent.load_session(meta.session_id)
                except SessionConfigMismatchError as e:
                    render.print_error(str(e))
                    continue
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

    session = await _pick_session(agent)

    if session is None:
        render.print_info("Goodbye.")
        return

    render.print_info(f"Session: {session.session_id}")
    render.print_info("")

    await run_loop(agent, session)
