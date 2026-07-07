"""App (minimal_agent.server) — sessions CRUD, SSE chat, registry routing,
user-route precedence over the UI mount."""

import json

import pytest
from fastapi.testclient import TestClient

from minimal_agent import App
from minimal_agent.agent import Agent
from minimal_agent.llm.types import GenerateResponse, StreamChunk, Usage

# --- Stub LLM -----------------------------------------------------------


class StubLLM:
    """Duck-typed LLM: streams a fixed reply in two chunks, no tool calls."""

    def __init__(self, text: str = "Hello from stub."):
        self.model = "stub-model"
        self.backend = "openai"
        self.text = text

    async def generate(self, *, messages, tools=None, tool_choice=None):
        return GenerateResponse(text=self.text, usage=self._usage())

    async def stream(self, *, messages, tools=None, tool_choice=None):
        mid = len(self.text) // 2
        yield StreamChunk(text=self.text[:mid])
        yield StreamChunk(text=self.text[mid:])
        yield StreamChunk(finish_reason="stop", usage=self._usage())

    def _usage(self) -> Usage:
        return Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)


def make_agent(workspace, text: str = "Hello from stub.") -> Agent:
    return Agent(
        llm=StubLLM(text),
        tools=[],
        prompt="You are a test agent.",
        context_sources=[],
        workspace_root=workspace,
    )


def make_app(tmp_path, agents=None, **kwargs) -> App:
    if agents is None:
        agents = make_agent(tmp_path / "ws")
    (tmp_path / "ws").mkdir(exist_ok=True)
    return App(agents=agents, sessions_dir=tmp_path / "sessions", **kwargs)


@pytest.fixture(autouse=True)
def _reset_sse_appstatus():
    """sse-starlette keeps a class-level exit event bound to the first
    event loop that runs a response; TestClient spins a fresh loop per
    context, so reset it between tests."""
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit_event = None
    yield
    AppStatus.should_exit_event = None


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into (event, data) pairs, ignoring pings."""
    events = []
    event = None
    for line in body.splitlines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and event is not None:
            events.append((event, json.loads(line.split(":", 1)[1].strip())))
            event = None
    return events


# --- Basics --------------------------------------------------------------


def test_health_and_config(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}

        config = client.get("/api/config").json()
        assert config["default_agent"] == "default"
        (agent_info,) = config["agents"]
        assert agent_info["name"] == "default"
        assert agent_info["model"] == "stub-model"
        assert agent_info["backend"] == "openai"
        assert agent_info["workspace_root"] == str(tmp_path / "ws")
        assert agent_info["tools"] == []


def test_agents_and_tools_listing(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        agents = client.get("/api/agents").json()["agents"]
        assert agents == [{"name": "default", "display_name": "Default"}]

        tools = client.get("/api/tools").json()["tools"]
        assert tools == []

        assert client.get("/api/tools", params={"agent": "nope"}).status_code == 404


# --- Sessions CRUD -------------------------------------------------------


def test_session_lifecycle(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        created = client.post("/api/sessions", json={})
        assert created.status_code == 201
        session = created.json()
        assert session["agent"] == "default"
        assert session["workspace_root"] == str(tmp_path / "ws")
        assert session["model"] == "stub-model"
        session_id = session["session_id"]

        listed = client.get("/api/sessions").json()["sessions"]
        assert [s["session_id"] for s in listed] == [session_id]
        assert listed[0]["agent"] == "default"

        fetched = client.get(f"/api/sessions/{session_id}")
        assert fetched.status_code == 200
        assert fetched.json()["session_id"] == session_id

        assert client.delete(f"/api/sessions/{session_id}").status_code == 204
        assert client.get(f"/api/sessions/{session_id}").status_code == 404
        assert client.delete(f"/api/sessions/{session_id}").status_code == 404


def test_create_session_unknown_agent(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post("/api/sessions", json={"agent": "nope"})
        assert resp.status_code == 404


def test_multi_agent_requires_name(tmp_path):
    agents = {
        "alpha": make_agent(tmp_path / "ws", text="I am alpha."),
        "beta": make_agent(tmp_path / "ws", text="I am beta."),
    }
    app = make_app(tmp_path, agents=agents)
    with TestClient(app) as client:
        assert client.post("/api/sessions", json={}).status_code == 422
        resp = client.post("/api/sessions", json={"agent": "beta"})
        assert resp.status_code == 201
        assert resp.json()["agent"] == "beta"


# --- Chat (SSE) ----------------------------------------------------------


def test_chat_streams_and_persists(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        session_id = client.post("/api/sessions", json={}).json()["session_id"]

        resp = client.post(f"/api/sessions/{session_id}/chat", json={"message": "hi"})
        assert resp.status_code == 200
        events = parse_sse(resp.text)

        deltas = "".join(d["text"] for e, d in events if e == "delta")
        assert deltas == "Hello from stub."

        assistants = [d for e, d in events if e == "assistant"]
        assert len(assistants) == 1
        assert assistants[0]["content"] == "Hello from stub."

        (done,) = [d for e, d in events if e == "done"]
        assert done["usage"]["total_tokens"] == 15

        # History persisted: user turn + committed assistant turn.
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["user", "assistant"]
        assert messages[1]["content"] == "Hello from stub."


def test_chat_routes_to_session_agent(tmp_path):
    agents = {
        "alpha": make_agent(tmp_path / "ws", text="I am alpha."),
        "beta": make_agent(tmp_path / "ws", text="I am beta."),
    }
    app = make_app(tmp_path, agents=agents)
    with TestClient(app) as client:
        session_id = client.post("/api/sessions", json={"agent": "beta"}).json()[
            "session_id"
        ]
        resp = client.post(
            f"/api/sessions/{session_id}/chat", json={"message": "who are you"}
        )
        assistants = [d for e, d in parse_sse(resp.text) if e == "assistant"]
        assert assistants[0]["content"] == "I am beta."


def test_chat_unknown_session_is_404(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post("/api/sessions/nope/chat", json={"message": "hi"})
        assert resp.status_code == 404


# --- User extension and UI mount -----------------------------------------


def _without_static(monkeypatch, tmp_path):
    """Point the App at an empty static dir so tests don't depend on
    whether `make ui` has been run in this checkout."""
    import minimal_agent.server.app as server_app

    monkeypatch.setattr(server_app, "_STATIC_DIR", tmp_path / "no-static")


def test_user_routes_win_over_ui_mount(tmp_path, monkeypatch):
    _without_static(monkeypatch, tmp_path)
    app = make_app(tmp_path)

    @app.get("/custom")
    def custom():
        return {"custom": True}

    with TestClient(app) as client:
        # User route registered after construction still resolves — the UI
        # mount is appended at startup, behind everything else.
        assert client.get("/custom").json() == {"custom": True}
        assert client.get("/api/health").status_code == 200

        # No bundled static → fallback page at /.
        root = client.get("/")
        assert root.status_code == 200
        assert "make ui" in root.text


def test_bundled_ui_served_at_root(tmp_path, monkeypatch):
    import minimal_agent.server.app as server_app

    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html><body>bundled ui</body></html>")
    monkeypatch.setattr(server_app, "_STATIC_DIR", static)

    app = make_app(tmp_path)
    with TestClient(app) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert "bundled ui" in root.text
        # API still wins over the catch-all static mount.
        assert client.get("/api/health").status_code == 200


def test_user_lifespan_composes(tmp_path, monkeypatch):
    _without_static(monkeypatch, tmp_path)
    from contextlib import asynccontextmanager

    seen = []

    @asynccontextmanager
    async def user_lifespan(app):
        seen.append("start")
        yield
        seen.append("stop")

    app = make_app(tmp_path, lifespan=user_lifespan)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert seen == ["start"]
        # UI fallback still mounted even with a user lifespan.
        assert "make ui" in client.get("/").text
    assert seen == ["start", "stop"]


def test_single_agent_normalizes_to_default(tmp_path):
    (tmp_path / "ws").mkdir(exist_ok=True)
    agent = make_agent(tmp_path / "ws")
    app = App(agents=agent, sessions_dir=tmp_path / "sessions")
    assert list(app.agents) == ["default"]
    # Registration rebinds session storage onto the App's store.
    assert agent.sessions is app.session_manager


def test_empty_registry_rejected(tmp_path):
    with pytest.raises(ValueError):
        App(agents={}, sessions_dir=tmp_path / "sessions")
