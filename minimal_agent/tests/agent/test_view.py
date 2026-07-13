"""SessionView — the inside view of a session.

The load-bearing property under test: everything session-specific reaches a
tool or a source through the env, per call, so one Agent can serve N
sessions with zero cross-talk. See
[.claude/specifications/session-env.md](../../.claude/specifications/session-env.md).
"""

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from minimal_agent.agent import Context, SessionManager, SessionView
from minimal_agent.agent.scope import NullScope
from minimal_agent.context_sources import Placement
from minimal_agent.events import SourceFailed
from minimal_agent.llm.types import Message, Role, ToolCall
from minimal_agent.tools import BaseTool, ToolContext


def _manager(tmp_path: Path) -> SessionManager:
    return SessionManager(base_dir=tmp_path / "sessions")


def _session(tmp_path: Path, workspace_root: Path | None = None, **kwargs):
    return _manager(tmp_path).create_session(
        model="test-model",
        backend="openai",
        workspace_root=str(workspace_root) if workspace_root else None,
        **kwargs,
    )


# ---- Transcript: read-only by construction ----------------------------------


class TestTranscript:
    def test_mirrors_the_store(self, tmp_path):
        ctx = _session(tmp_path).context
        ctx.add(Message(role=Role.USER, content="one"))
        ctx.add(Message(role=Role.ASSISTANT, content="two"))

        assert len(ctx.session.transcript) == 2
        assert ctx.session.transcript[0].content == "one"
        assert [m.content for m in ctx.session.transcript] == ["one", "two"]

    def test_is_live_not_a_snapshot(self, tmp_path):
        """A tool sees the messages that preceded it in the current turn."""
        ctx = _session(tmp_path).context
        transcript = ctx.session.transcript
        assert len(transcript) == 0

        ctx.add(Message(role=Role.USER, content="later"))
        assert len(transcript) == 1

    def test_has_no_mutating_method(self, tmp_path):
        """The footgun is unrepresentable, not merely documented against:
        a source appending mid-assemble() would corrupt the transcript."""
        transcript = _session(tmp_path).context.session.transcript

        assert not hasattr(transcript, "append")
        with pytest.raises(TypeError):
            transcript[0] = Message(role=Role.USER, content="nope")

    def test_tool_calls_filters_by_name(self, tmp_path):
        ctx = _session(tmp_path).context
        ctx.add(
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(id="1", name="browser", arguments={"step": 1}),
                    ToolCall(id="2", name="grep", arguments={}),
                ],
            )
        )
        ctx.add(
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(id="3", name="browser", arguments={"step": 2})],
            )
        )

        assert [c.id for c in ctx.session.transcript.tool_calls()] == ["1", "2", "3"]
        browser = ctx.session.transcript.tool_calls(name="browser")
        assert [c.arguments["step"] for c in browser] == [1, 2]

    def test_tool_calls_empty_for_plain_conversation(self, tmp_path):
        ctx = _session(tmp_path).context
        ctx.add(Message(role=Role.USER, content="hi"))
        assert ctx.session.transcript.tool_calls() == []


# ---- state_dir: always a real, writable directory ---------------------------


class TestStateDir:
    def test_recorded_session_gets_state_under_the_session_dir(self, tmp_path):
        session = _session(tmp_path)

        state = session.context.session.state_dir

        assert state == session.session_dir / "state"
        assert state.is_dir()

    def test_bare_context_gets_a_tempdir(self, tmp_path):
        """Unrecorded degrades to amnesiac, never to crippled: state_dir is
        still a real writable path, it just evaporates."""
        view = Context().session

        state = view.state_dir

        assert state.is_dir()
        (state / "note.txt").write_text("scratch")
        assert (state / "note.txt").read_text() == "scratch"

    def test_bare_contexts_get_distinct_tempdirs(self):
        assert Context().session.state_dir != Context().session.state_dir

    def test_survives_resume(self, tmp_path):
        """The session-memory pattern: written in run 1, read in run 40.
        No rebuild step, no host wiring — persistence locates itself."""
        manager = _manager(tmp_path)
        session = manager.create_session(model="test-model", backend="openai")
        (session.context.session.state_dir / "notes.md").write_text("- remember this\n")

        loaded = manager.load_session(
            session.session_id, model="test-model", backend="openai"
        )

        notes = loaded.context.session.state_dir / "notes.md"
        assert notes.read_text() == "- remember this\n"

    def test_is_never_none(self, tmp_path):
        """No consumer ever branches on presence — recorded or bare."""
        for view in (_session(tmp_path).context.session, Context().session):
            assert isinstance(view.state_dir, Path)
            assert view.state_dir.is_dir()


# ---- identity ---------------------------------------------------------------


class TestIdentity:
    def test_recorded_session_carries_its_id_and_root(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        session = _session(tmp_path, workspace_root=ws)

        view = session.context.session

        assert view.id == session.session_id
        assert view.workspace_root == ws

    def test_bare_context_has_no_session_id(self):
        assert Context().session.id is None


# ---- wiring: one env per Context, reaching both surfaces --------------------


class _In(BaseModel):
    pass


class _EnvCapturingTool(BaseTool[_In, str]):
    name = "capture_env"
    input_schema = _In

    def __init__(self) -> None:
        self.seen: SessionView | None = None

    async def invoke(self, args: _In, ctx: ToolContext) -> str:
        self.seen = ctx.session
        return "ok"


class _EnvCapturingSource:
    name = "capture"
    placement = Placement.RUN

    def __init__(self) -> None:
        self.seen: SessionView | None = None

    async def gather(self, session: SessionView) -> str | None:
        self.seen = session
        return None


class TestWiring:
    async def test_tool_receives_the_contexts_env(self, tmp_path):
        from minimal_agent.tools import dispatch

        session = _session(tmp_path)
        tool = _EnvCapturingTool()

        await dispatch(
            ToolCall(id="c1", name="capture_env", arguments={}),
            {"capture_env": tool},
            ToolContext(session=session.context.session),
        )

        # Identity, not equality: the very same env object.
        assert tool.seen is session.context.session

    async def test_gather_receives_the_contexts_env(self, tmp_path):
        source = _EnvCapturingSource()
        session = _session(tmp_path, context_sources=[source])
        session.context.add(Message(role=Role.USER, content="hi"))

        await session.context.assemble()

        assert source.seen is session.context.session

    def test_one_env_per_context_for_its_lifetime(self, tmp_path):
        ctx = _session(tmp_path).context
        assert ctx.session is ctx.session


# ---- the load-bearing test: multi-session correctness ------------------------


class _RememberTool(BaseTool[_In, str]):
    """Stateful by design — and session-correct anyway, because all
    session-specific data arrives through the env, never the constructor."""

    name = "remember"
    input_schema = _In

    def __init__(self, note: str) -> None:
        self._note = note  # config, not state

    async def invoke(self, args: _In, ctx: ToolContext) -> str:
        with (ctx.session.state_dir / "notes.jsonl").open("a") as f:
            f.write(json.dumps({"note": self._note}) + "\n")
        return "ok"


class _NotesSource:
    """Reads back what the tool wrote — impossible to write before the env,
    which is the whole point."""

    name = "notes"
    placement = Placement.RUN

    async def gather(self, session: SessionView) -> str | None:
        path = session.state_dir / "notes.jsonl"
        if not path.exists():
            return None
        return "\n".join(
            json.loads(line)["note"] for line in path.read_text().splitlines()
        )


async def test_two_concurrent_sessions_never_cross_contaminate(tmp_path):
    """One agent, two live sessions, a stateful tool writing to state_dir and
    a source reading it back. Each session sees exactly its own notes."""
    from minimal_agent.tools import dispatch

    manager = _manager(tmp_path)
    source = _NotesSource()  # ONE source object, serving both sessions

    def new_session(note: str):
        return manager.create_session(
            model="test-model", backend="openai", context_sources=[source]
        )

    s1, s2 = new_session("alpha"), new_session("beta")

    async def run(session, note: str) -> str:
        tool = _RememberTool(note)
        await dispatch(
            ToolCall(id="c", name="remember", arguments={}),
            {"remember": tool},
            ToolContext(session=session.context.session),
        )
        session.context.add(Message(role=Role.USER, content="what do you know?"))
        msgs = await session.context.assemble()
        return msgs[-1].content

    a, b = await asyncio.gather(run(s1, "alpha"), run(s2, "beta"))

    assert "alpha" in a and "beta" not in a
    assert "beta" in b and "alpha" not in b
    # And the state landed in each session's own directory.
    assert (s1.session_dir / "state" / "notes.jsonl").exists()
    assert (s2.session_dir / "state" / "notes.jsonl").exists()


# ---- events: user code participates in the trace ----------------------------
#
# NOTE: `Event` is a closed Union of framework events, so a user CANNOT yet
# define a novel event type — the env hands out the emitter, but the taxonomy
# is sealed. Opening it up (an event base class + sink dispatch that tolerates
# unknown types) is its own change; see the spec's extension gallery #4.


async def test_env_emitter_writes_to_the_session_trace(tmp_path):
    session = _session(tmp_path)

    session.context.session.events.emit(SourceFailed(source="flaky", error="OSError"))

    trace = (session.session_dir / "events.jsonl").read_text()
    assert '"source.failed"' in trace
    assert '"flaky"' in trace


def test_bare_view_emit_is_a_no_op():
    """Fire-and-forget: emitting on an unrecorded env goes nowhere, safely."""
    Context().session.events.emit(SourceFailed(source="flaky", error="OSError"))


# ---- spawn: the one door back into the recording tree -----------------------


class TestSpawn:
    def test_child_env_has_its_own_state_and_transcript(self, tmp_path):
        session = _session(tmp_path)
        session.context.add(Message(role=Role.USER, content="parent msg"))

        with session.context.session.spawn(spawned_by="t", task="sub") as scope:
            child = scope.new_context(behavior_prompt="child")

            # Private by default, mirroring how its transcript already works.
            assert child.session.state_dir != session.context.session.state_dir
            assert child.session.state_dir.is_dir()
            assert len(child.session.transcript) == 0
            assert len(session.context.session.transcript) == 1

    def test_bare_view_spawn_degrades_to_null(self):
        with Context().session.spawn(spawned_by="t", task="sub") as scope:
            assert isinstance(scope, NullScope)
