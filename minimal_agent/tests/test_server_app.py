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


class ReasoningStubLLM(StubLLM):
    """Streams a thinking trace ahead of the answer, then commits both."""

    async def stream(self, *, messages, tools=None, tool_choice=None):
        yield StreamChunk(reasoning="Let me ")
        yield StreamChunk(reasoning="think.")
        mid = len(self.text) // 2
        yield StreamChunk(text=self.text[:mid])
        yield StreamChunk(text=self.text[mid:])
        yield StreamChunk(finish_reason="stop", usage=self._usage())


def test_chat_streams_reasoning_and_persists(tmp_path):
    agent = Agent(
        llm=ReasoningStubLLM(),
        tools=[],
        prompt="You are a test agent.",
        context_sources=[],
        workspace_root=tmp_path / "ws",
    )
    app = make_app(tmp_path, agents=agent)
    with TestClient(app) as client:
        session_id = client.post("/api/sessions", json={}).json()["session_id"]

        resp = client.post(f"/api/sessions/{session_id}/chat", json={"message": "hi"})
        events = parse_sse(resp.text)

        # Reasoning streams on its own channel, ahead of the answer deltas.
        reasoning = "".join(d["text"] for e, d in events if e == "reasoning")
        assert reasoning == "Let me think."
        deltas = "".join(d["text"] for e, d in events if e == "delta")
        assert deltas == "Hello from stub."

        # The committed assistant message carries the full trace.
        (assistant,) = [d for e, d in events if e == "assistant"]
        assert assistant["reasoning"] == "Let me think."

        # History round-trips the trace.
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["messages"]
        assert messages[1]["reasoning"] == "Let me think."


class ToolCallStubLLM(StubLLM):
    """Streams a tool call in argument fragments, then answers with text.

    Mimics OpenAI's wire shape: the first fragment carries id + name, the
    rest carry incremental JSON string chunks of the arguments.
    """

    async def stream(self, *, messages, tools=None, tool_choice=None):
        from minimal_agent.llm.types import ToolCallDelta

        # First turn: emit a tool call. Second turn (after the tool result
        # lands in history): emit the final answer.
        if not any(m.role.value == "tool" for m in messages):
            yield StreamChunk(
                tool_calls=[ToolCallDelta(index=0, id="call_1", name="echo")]
            )
            yield StreamChunk(tool_calls=[ToolCallDelta(index=0, arguments='{"tex')])
            yield StreamChunk(
                tool_calls=[ToolCallDelta(index=0, arguments='t": "hi"}')]
            )
            yield StreamChunk(finish_reason="tool_calls", usage=self._usage())
        else:
            yield StreamChunk(text=self.text)
            yield StreamChunk(finish_reason="stop", usage=self._usage())


def test_chat_streams_tool_call_deltas(tmp_path):
    from typing import ClassVar

    from pydantic import BaseModel

    from minimal_agent.tools.base import BaseTool
    from minimal_agent.tools.context import ToolContext

    class EchoInput(BaseModel):
        text: str

    class EchoTool(BaseTool[EchoInput, str]):
        name: ClassVar[str] = "echo"
        input_schema: ClassVar[type[BaseModel]] = EchoInput

        async def invoke(self, args: EchoInput, ctx: ToolContext) -> str:
            return args.text

    agent = Agent(
        llm=ToolCallStubLLM(),
        tools=[EchoTool()],
        prompt="You are a test agent.",
        context_sources=[],
        workspace_root=tmp_path / "ws",
    )
    app = make_app(tmp_path, agents=agent)
    with TestClient(app) as client:
        session_id = client.post("/api/sessions", json={}).json()["session_id"]

        resp = client.post(f"/api/sessions/{session_id}/chat", json={"message": "hi"})
        events = parse_sse(resp.text)

        # Argument fragments stream on their own channel, in order.
        deltas = [d["tool_calls"] for e, d in events if e == "tool_call_delta"]
        assert deltas == [
            [{"index": 0, "id": "call_1", "name": "echo"}],
            [{"index": 0, "arguments": '{"tex'}],
            [{"index": 0, "arguments": 't": "hi"}'}],
        ]

        # The committed assistant message carries the assembled call, and the
        # fragments concatenate to exactly its argument JSON.
        first_assistant = next(d for e, d in events if e == "assistant")
        assert first_assistant["tool_calls"][0]["arguments"] == {"text": "hi"}

        (tool_result,) = [d for e, d in events if e == "tool_result"]
        assert tool_result["content"] == "hi"


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
