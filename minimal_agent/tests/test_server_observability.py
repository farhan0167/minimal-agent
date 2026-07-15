"""Observability routes — the audit surface over the session artifacts.

The regression these guard: `unverified_reason` is the field that tells a
client *why* a call could not be verified. The library has always produced it;
the HTTP layer used to drop it, so an unverifiable call reached the client as a
bare `verified: false` plus a lone system prompt — which reads as "the
framework lost my conversation" rather than "this run never completed".

Both call-shaped schemas carry it, and both mappers are tested: the nested
`/runs/{run_id}` shape is the one a real client hits, and a fix applied only to
the single-call mapper would leave it broken while looking green.
"""

import json

import pytest
from fastapi.testclient import TestClient

from minimal_agent import App
from minimal_agent.agent import Agent
from minimal_agent.agent.context import Context
from minimal_agent.agent.session import SessionManager
from minimal_agent.events import RunEnd, RunEndStatus, RunStart
from minimal_agent.llm.types import Message, Role


class StubLLM:
    def __init__(self):
        self.model = "test-model"
        self.backend = "openai"


class _ElidingContext(Context):
    """A miniature of a real context-managing subclass: identity below a
    threshold, rewriting (model_copy) above it. Past four stored messages it
    redacts all but the last two — the projection the ranges-only recipe could
    not express, and the one that produced the original bug report."""

    THRESHOLD = 4

    def project(self):
        msgs = self._store.messages
        if len(msgs) <= self.THRESHOLD:
            return msgs
        return [
            *(
                m.model_copy(update={"content": f"[elided {m.content}]"})
                for m in msgs[:-2]
            ),
            *msgs[-2:],
        ]


async def _recorded_session(tmp_path, *, calls=2):
    """A session with `calls` recorded LLM calls under the eliding context:
    the first below the rewrite threshold, the rest above it."""
    manager = SessionManager(base_dir=tmp_path / "sessions")
    session = manager.create_session(
        model="test-model",
        backend="openai",
        behavior_prompt="you are helpful",
        context_cls=_ElidingContext,
    )
    events = session.context.events
    events.emit(
        RunStart(
            model="test-model",
            backend="openai",
            tools_json="[]",
            system_prompt="you are helpful",
            store_len=0,
        )
    )
    # Call 1: three messages, below the threshold — a pure selection.
    for i in range(3):
        session.context.add(Message(role=Role.USER, content=f"m{i}"))
    await session.context.assemble()
    # Call 2+: past the threshold, so project() rewrites.
    for i in range(3, 3 + calls):
        session.context.add(Message(role=Role.USER, content=f"m{i}"))
        await session.context.assemble()
    events.emit(RunEnd(status=RunEndStatus.COMPLETED, calls=calls + 1, duration_ms=1))
    return session


def _client(tmp_path) -> TestClient:
    (tmp_path / "ws").mkdir(exist_ok=True)
    agent = Agent(
        llm=StubLLM(),
        tools=[],
        prompt="You are a test agent.",
        context_sources=[],
        workspace_root=tmp_path / "ws",
    )
    return TestClient(App(agents=agent, sessions_dir=tmp_path / "sessions"))


@pytest.fixture
async def session_and_client(tmp_path):
    session = await _recorded_session(tmp_path)
    return session, _client(tmp_path)


async def test_rewritten_call_verifies_over_the_wire(session_and_client):
    """A rewriting projection is reconstructible (record v3 quotes the
    rewritten messages by value), so it verifies through the API — with no
    reason to report and the elided content intact."""
    session, client = session_and_client
    calls = client.get(f"/api/sessions/{session.session_id}/calls").json()["calls"]
    rewritten = calls[-1]["call_id"]

    body = client.get(f"/api/sessions/{session.session_id}/calls/{rewritten}").json()

    assert body["verified"] is True
    assert body["unverified_reason"] is None
    contents = [m["content"] for m in body["messages"]]
    assert "[elided m0]" in contents  # the rewrite, rebuilt from its blob
    assert "m0" not in contents  # ...and not the original it replaced


async def test_verified_call_carries_the_reason_field_as_null(session_and_client):
    """Schema honesty: the field is present-and-null on a verified call, never
    absent, so a client can key off it without an existence check."""
    session, client = session_and_client
    calls = client.get(f"/api/sessions/{session.session_id}/calls").json()["calls"]

    body = client.get(
        f"/api/sessions/{session.session_id}/calls/{calls[0]['call_id']}"
    ).json()

    assert body["verified"] is True
    assert "unverified_reason" in body
    assert body["unverified_reason"] is None


async def test_unverifiable_call_reports_its_reason(tmp_path):
    """The regression, on the single-call route: a call whose run never closed
    cannot recover its system prompt. The API says so, rather than returning a
    bare `verified: false` that reads as a corrupt transcript."""
    session = await _recorded_session(tmp_path)
    # Drop runs.jsonl: the run never completed, so the system prompt — a
    # run-level fact — is unrecoverable. This is the reason's other producer.
    (session.session_dir / "runs.jsonl").unlink()
    client = _client(tmp_path)
    calls = client.get(f"/api/sessions/{session.session_id}/calls").json()["calls"]

    body = client.get(
        f"/api/sessions/{session.session_id}/calls/{calls[0]['call_id']}"
    ).json()

    assert body["verified"] is False
    assert "run did not complete" in body["unverified_reason"]


async def test_unverifiable_call_reports_its_reason_when_nested_under_a_run(tmp_path):
    """The same regression on the nested `/runs/{run_id}` shape — the one a
    real client reads, and the one a fix applied only to the single-call mapper
    would silently miss. Both mappers, or neither."""
    session = await _recorded_session(tmp_path)
    run_id = json.loads(
        (session.session_dir / "calls.jsonl").read_text().splitlines()[0]
    )["run_id"]
    (session.session_dir / "runs.jsonl").unlink()
    client = _client(tmp_path)

    run = client.get(f"/api/sessions/{session.session_id}/runs/{run_id}").json()

    assert run["calls"]
    for call in run["calls"]:
        assert call["input"]["verified"] is False
        assert "run did not complete" in call["input"]["unverified_reason"]


async def test_legacy_null_projection_reports_its_reason(tmp_path):
    """A pre-v3 record whose rewriting projection had no range expression: the
    bytes were never persisted, so it stays unverifiable — and the API now
    names the projection as the cause instead of leaving the client to guess."""
    session = await _recorded_session(tmp_path)
    path = session.session_dir / "calls.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    records[-1]["v"] = 2
    records[-1]["projected"] = None
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    client = _client(tmp_path)

    call_id = records[-1]["call_id"]
    body = client.get(f"/api/sessions/{session.session_id}/calls/{call_id}").json()

    assert body["verified"] is False
    assert "not expressible as store ranges" in body["unverified_reason"]
    # `messages` stays partial, not emptied: the system prompt was truthfully
    # recovered from the run record's blob. The reason field is what tells a
    # client not to read it as the full input.
    assert [m["role"] for m in body["messages"]] == ["system"]
