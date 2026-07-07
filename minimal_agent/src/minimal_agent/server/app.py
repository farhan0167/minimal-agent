"""App — a FastAPI subclass that serves registered Agents over HTTP/SSE
with a bundled web UI.

    from minimal_agent import Agent, App

    agent = Agent(llm=..., tools=[...], workspace_root=Path.cwd())
    app = App(agents=agent)

    if __name__ == "__main__":
        app.serve()   # → http://localhost:8000 — API under /api, chat UI at /

Because App *is* a FastAPI, everything FastAPI works untouched: add
routes with @app.get(...), middleware, dependencies, and
`uvicorn my_app:app --reload` for hot reload.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..agent import Agent, SessionManager
from ..config import settings
from ..events import Sink
from .routes import api_router

_STATIC_DIR = Path(__file__).parent / "static"

_FALLBACK_HTML = """<!doctype html>
<html>
  <head><title>minimal-agent</title></head>
  <body style="font-family: system-ui, sans-serif; max-width: 40rem;
               margin: 4rem auto; line-height: 1.6; color: #1a1a18;">
    <h1>minimal-agent</h1>
    <p>The API is live — interactive docs at <a href="/docs">/docs</a>,
       endpoints under <code>/api</code>.</p>
    <p>The web UI isn't bundled in this install. Running from a source
       checkout? Build it once with <code>make ui</code> at the repo root,
       then restart.</p>
  </body>
</html>
"""


def _normalize_agents(agents: Agent | dict[str, Agent]) -> dict[str, Agent]:
    if isinstance(agents, Agent):
        return {"default": agents}
    if not agents:
        raise ValueError("App requires at least one agent")
    return dict(agents)


class App(FastAPI):
    """FastAPI + an agent registry + pre-wired agent routes + a bundled UI.

    Args:
        agents: A single Agent, or a dict mapping names to Agents. Names
            appear in the UI's agent picker and in the per-session sidecar.
        sessions_dir: Where sessions are stored. Every registered agent is
            rebound to one SessionManager here, so all sessions live in a
            single consistent store. Defaults to settings.SESSIONS_DIR.
        extra_sinks: Extra event sinks wired into every session the App
            creates — e.g. a PhoenixSink to export OpenTelemetry spans. They
            ride the same seam the local artifacts do and reach every nested
            agent scope; a failing sink can never break a run.
        **fastapi_kwargs: Passed through to FastAPI (title, version,
            lifespan, ...).
    """

    def __init__(
        self,
        *,
        agents: Agent | dict[str, Agent],
        sessions_dir: str | Path | None = None,
        extra_sinks: list[Sink] | None = None,
        **fastapi_kwargs,
    ) -> None:
        fastapi_kwargs.setdefault("title", "minimal-agent")

        # The UI mount must be appended to the route table *after* every
        # user-registered route (a "/" mount matches all paths, so routes
        # added behind it would be shadowed). Startup is the one moment
        # that is reliably after all registration, so the mount rides the
        # lifespan — wrapping the user's own lifespan when one is given.
        user_lifespan = fastapi_kwargs.pop("lifespan", None)

        @asynccontextmanager
        async def _lifespan(app: FastAPI):
            self._mount_ui()
            if user_lifespan is not None:
                async with user_lifespan(app):
                    yield
            else:
                yield

        super().__init__(lifespan=_lifespan, **fastapi_kwargs)

        self.agents: dict[str, Agent] = _normalize_agents(agents)
        base_dir = Path(sessions_dir) if sessions_dir else Path(settings.SESSIONS_DIR)
        self.session_manager = SessionManager(
            base_dir=base_dir, extra_sinks=extra_sinks
        )
        # One store for every agent — sessions created by any of them are
        # listable and resumable through this App.
        for agent in self.agents.values():
            agent.sessions = self.session_manager

        self.include_router(api_router, prefix="/api")
        self._ui_mounted = False

    def _mount_ui(self) -> None:
        """Serve the bundled web UI at /, or a pointer page without it."""
        if self._ui_mounted:
            return
        self._ui_mounted = True
        if (_STATIC_DIR / "index.html").is_file():
            self.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="ui")
        else:

            async def fallback(request):
                return HTMLResponse(_FALLBACK_HTML)

            self.add_route("/", fallback, methods=["GET"], include_in_schema=False)

    def serve(self, host: str = "0.0.0.0", port: int = 8000, **uvicorn_kwargs):
        """Run the app with uvicorn. Blocks until interrupted."""
        if uvicorn_kwargs.get("reload"):
            raise ValueError(
                "reload needs an import string, not a live app — run "
                "`uvicorn my_app:app --reload` instead"
            )
        import uvicorn

        uvicorn.run(self, host=host, port=port, **uvicorn_kwargs)
