"""Tests for the recording tree — Scope, child scopes, and rollups.

Covers the spec's guarantees: children get the full artifact kit under the
session, linkage is bidirectional, agent.end is truthful on every exit
path, usage forwards to the session root, and everything degrades to
NullScope instead of breaking the run.
"""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from minimal_agent.agent.scope import NullScope, RecordedScope
from minimal_agent.agent.session import SessionManager
from minimal_agent.agent.sinks import BlobStore
from minimal_agent.agent.view import SessionView
from minimal_agent.events import CallResponse, RunStart
from minimal_agent.llm.types import (
    GenerateResponse,
    Message,
    Role,
    ToolCall,
    Usage,
)
from minimal_agent.tools import BaseTool, ToolContext, dispatch
from minimal_agent.tools.builtin.spawn_agents.schema import (
    SpawnAgentsInput,
    SubAgentSpec,
)
from minimal_agent.tools.builtin.spawn_agents.tool import SpawnAgents


def _root_scope(tmp_path, session_id="sess-1") -> RecordedScope:
    return RecordedScope(
        tmp_path, blobs=BlobStore(tmp_path / "blobs"), session_id=session_id
    )


def _events(scope_dir) -> list[dict]:
    return [
        json.loads(line)
        for line in (scope_dir / "events.jsonl").read_text().splitlines()
    ]


def _agent_json(root, agent_id) -> dict:
    return json.loads((root / "agents" / agent_id / "agent.json").read_text())


def _usage(n=100) -> Usage:
    return Usage(prompt_tokens=n, completion_tokens=n // 2, total_tokens=n + n // 2)


# ---- child lifecycle ---------------------------------------------------------


def test_child_allocates_artifact_kit_and_links_both_ways(tmp_path):
    root = _root_scope(tmp_path)

    with root.child(
        spawned_by="spawn_agents", task="audit errors", tool_call_id="call_1"
    ) as child:
        child.store.append(Message(role=Role.USER, content="hi"))
        (agent_id,) = root.children_of("call_1")

    # Child transcript landed under the session.
    child_dir = tmp_path / "agents" / agent_id
    assert (child_dir / "messages.jsonl").exists()

    # Upward link: agent.json carries full parentage.
    meta = _agent_json(tmp_path, agent_id)
    assert meta["spawned_by"] == "spawn_agents"
    assert meta["task"] == "audit errors"
    assert meta["parent"]["session_id"] == "sess-1"
    assert meta["parent"]["tool_call_id"] == "call_1"
    assert meta["status"] == "completed"
    assert meta["ended_at"] >= meta["created_at"]

    # Downward link: agent.spawn / agent.end in the parent's trace.
    spawn, end = _events(tmp_path)
    assert spawn["type"] == "agent.spawn"
    assert spawn["payload"]["agent_id"] == agent_id
    assert end["type"] == "agent.end"
    assert end["payload"]["status"] == "completed"


def test_child_error_leaves_truthful_record_and_reraises(tmp_path):
    root = _root_scope(tmp_path)

    with pytest.raises(RuntimeError):
        with root.child(spawned_by="t", task="x"):
            raise RuntimeError("boom")

    end = _events(tmp_path)[-1]
    assert end["type"] == "agent.end"
    assert end["payload"]["status"] == "error"
    agent_id = end["payload"]["agent_id"]
    assert _agent_json(tmp_path, agent_id)["status"] == "error"


def test_child_cancellation_records_abandoned(tmp_path):
    root = _root_scope(tmp_path)

    with pytest.raises(asyncio.CancelledError):
        with root.child(spawned_by="t", task="x"):
            raise asyncio.CancelledError()

    end = _events(tmp_path)[-1]
    assert end["payload"]["status"] == "abandoned"


def test_child_degrades_to_null_scope_when_dir_uncreatable(tmp_path):
    root = _root_scope(tmp_path)
    (tmp_path / "agents").write_text("not a directory")  # mkdir will fail

    with root.child(spawned_by="t", task="x") as child:
        assert isinstance(child, NullScope)  # runs unrecorded, never raises


def test_nested_children_land_under_their_parent(tmp_path):
    root = _root_scope(tmp_path)

    with root.child(spawned_by="a", task="outer") as mid:
        with mid.child(spawned_by="b", task="inner"):
            pass
        (outer_id,) = root.children_of(None)

    inner_dirs = list((tmp_path / "agents" / outer_id / "agents").iterdir())
    assert len(inner_dirs) == 1
    assert (inner_dirs[0] / "agent.json").exists()


# ---- fingerprint + usage rollup ----------------------------------------------


def _report(scope, usage: Usage) -> None:
    scope.events.emit(
        CallResponse(latency_ms=1, usage=usage.model_dump(), tool_calls=0)
    )


def test_child_usage_forwards_to_root_and_agent_end(tmp_path):
    root = _root_scope(tmp_path)

    with root.child(spawned_by="t", task="x") as child:
        child.events.emit(
            RunStart(
                model="child-model",
                backend="openai",
                tools_json="[]",
                system_prompt=None,
                store_len=0,
            )
        )
        _report(child, _usage(100))
        _report(child, _usage(100))

    # Child's own totals rolled into agent.end and agent.json…
    end = _events(tmp_path)[-1]
    assert end["payload"]["usage"]["prompt_tokens"] == 200
    agent_id = end["payload"]["agent_id"]
    meta = _agent_json(tmp_path, agent_id)
    assert meta["usage"]["total_tokens"] == 300
    assert meta["model"] == "child-model"  # fingerprint captured from run.start

    # …and forwarded to the session root's totals.
    assert root.totals.usage.prompt_tokens == 200


def test_grandchild_usage_reaches_the_root(tmp_path):
    root = _root_scope(tmp_path)

    with root.child(spawned_by="a", task="outer") as mid:
        with mid.child(spawned_by="b", task="inner") as leaf:
            _report(leaf, _usage(100))

    assert root.totals.usage.prompt_tokens == 100


def test_session_json_includes_nested_agent_usage(tmp_path):
    session = SessionManager(base_dir=tmp_path).create_session(
        model="m", backend="openai"
    )

    with session.scope.child(spawned_by="t", task="x") as child:
        _report(child, _usage(100))

    meta = json.loads((session.session_dir / "session.json").read_text())
    assert meta["usage"]["prompt_tokens"] == 100
    assert session.usage.prompt_tokens == 100


async def test_child_blobs_share_the_session_root_store(tmp_path):
    session = SessionManager(base_dir=tmp_path).create_session(
        model="m", backend="openai", behavior_prompt="root sys"
    )

    # A run inside the child interns its system prompt against root blobs/.
    with session.scope.child(spawned_by="t", task="x") as child:
        child.events.emit(
            RunStart(
                model="m",
                backend="openai",
                tools_json="[]",
                system_prompt="child sys",
                store_len=0,
            )
        )

    record = json.loads((child.dir / "runs.jsonl").read_text().splitlines()[0])
    digest = record["system_prompt"].removeprefix("sha256:")
    assert (session.session_dir / "blobs" / digest).exists()
    assert not (child.dir / "blobs").exists()


# ---- dispatcher integration ----------------------------------------------------


async def test_tool_end_carries_children(tmp_path):
    from pydantic import BaseModel

    class _In(BaseModel):
        pass

    class SpawningTool(BaseTool[_In, str]):
        name = "spawner"
        input_schema = _In

        async def invoke(self, args: _In, ctx: ToolContext) -> str:
            with ctx.session.spawn(
                spawned_by=self.name, task="sub", tool_call_id=ctx.tool_call_id
            ):
                pass
            return "ok"

    root = _root_scope(tmp_path)
    ctx = ToolContext(session=SessionView(scope=root))
    call = ToolCall(id="call_9", name="spawner", arguments={})

    await dispatch(call, {"spawner": SpawningTool()}, ctx)

    end = next(e for e in _events(tmp_path) if e["type"] == "tool.end")
    (agent_id,) = root.children_of("call_9")
    assert end["payload"]["children"] == [agent_id]


# ---- spawn_agents end to end ---------------------------------------------------


async def test_spawn_agents_records_children_under_the_scope(tmp_path):
    llm = AsyncMock()
    llm.model = "test-model"
    llm.backend = "openai"
    llm.generate.return_value = GenerateResponse(text="sub answer", tool_calls=None)

    tool = SpawnAgents(llm=llm, available_tools={}, workspace_root=tmp_path)
    root = _root_scope(tmp_path)
    ctx = ToolContext(session=SessionView(scope=root), tool_call_id="call_7")

    result = await tool.invoke(
        SpawnAgentsInput(
            agents=[
                SubAgentSpec(task="task one"),
                SubAgentSpec(task="task two"),
            ]
        ),
        ctx,
    )

    assert "sub answer" in result
    children = root.children_of("call_7")
    assert len(children) == 2
    for agent_id in children:
        child_dir = tmp_path / "agents" / agent_id
        # Full transcript: user task + assistant answer.
        lines = (child_dir / "messages.jsonl").read_text().splitlines()
        roles = [json.loads(line)["role"] for line in lines]
        assert roles == ["user", "assistant"]
        # Its own trace with a completed run.
        types = [e["type"] for e in _events(child_dir)]
        assert "run.start" in types and "run.end" in types
        # And a completed agent.json carrying the sub-agent's fingerprint.
        meta = _agent_json(tmp_path, agent_id)
        assert meta["status"] == "completed"
        assert meta["model"] == "test-model"
