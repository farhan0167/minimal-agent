"""Read-side utilities for the observability artifacts.

The write side (`events.py`, `agent/sinks.py`, `agent/scope.py`) records;
this module answers. `read_events()` returns the timeline,
`read_call_records()` the audit records, `reconstruct_call()` rebuilds —
byte-exactly — what the model saw on any recorded LLM call, and
`session_tree()` walks the whole recording tree, nested agents included.

Every function here takes a *scope* directory: the session root or any
`agents/<agent-id>/` directory under it — child scopes carry the identical
artifact kit, so the same readers apply one directory down. (Blob refs are
resolved upward: children share the session root's `blobs/`.)

Strictly read-only and never imported by request-path code (observability
invariant 2: regeneration stays the only source of live content). It exists
for hosts, debuggers, and audit tooling.

See
[.claude/specifications/observability.md](.claude/specifications/observability.md).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from .agent.context import _merge_into_user
from .events import hash_messages
from .llm.types import Message, Role


class CallRecordNotFoundError(LookupError):
    """No record with the requested call_id exists in calls.jsonl."""


def read_events(session_dir: Path) -> list[dict]:
    """The session's timeline: every envelope in events.jsonl, in emission
    order. Empty for sessions predating the trace."""
    return _read_jsonl(session_dir / "events.jsonl")


def read_call_records(session_dir: Path) -> list[dict]:
    """The session's audit records: one dict per LLM call, in call order.
    Empty for sessions predating the audit log."""
    return _read_jsonl(session_dir / "calls.jsonl")


@dataclass(frozen=True)
class ReconstructedCall:
    """One LLM call's exact input, rebuilt from the session directory.

    `verified` compares the recorded hash against one computed over the
    rebuilt messages. A mismatch means *unverifiable*, not *tampered* —
    the canonical serialization can drift across Pydantic/environment
    versions (see the spec's hash caveat).
    """

    call_id: str
    run_id: str | None
    ts: str
    model: str | None
    backend: str | None
    tools: list[dict] | None  # tool schemas the model was offered
    messages: list[Message]  # exactly what the model saw, in order
    recorded_sha256: str
    computed_sha256: str

    @property
    def verified(self) -> bool:
        return self.computed_sha256 == self.recorded_sha256


def reconstruct_call(session_dir: Path, call_id: str) -> ReconstructedCall:
    """Rebuild the exact model input for one recorded call.

    The audit recipe: system prompt from its blob, projected store ranges
    from messages.jsonl, injected blocks re-applied verbatim (framing is
    quoted in the record, so no framing constant is consulted). Raises
    CallRecordNotFoundError for an unknown call_id and FileNotFoundError
    if a referenced blob is missing (a dangling ref from a failed write).
    """
    record = next(
        (r for r in read_call_records(session_dir) if r["call_id"] == call_id),
        None,
    )
    if record is None:
        raise CallRecordNotFoundError(
            f"no call record {call_id!r} in {session_dir / 'calls.jsonl'}"
        )
    return _rebuild(session_dir, record, _read_stored(session_dir))


def _read_stored(session_dir: Path) -> list[Message]:
    return [
        Message.model_validate_json(line)
        for line in _read_lines(session_dir / "messages.jsonl")
    ]


def _rebuild(
    session_dir: Path, record: dict, stored: list[Message]
) -> ReconstructedCall:
    """Apply the audit recipe to one record against the loaded transcript."""
    msgs: list[Message] = []
    if record["system_prompt"]:
        msgs.append(
            Message(
                role=Role.SYSTEM,
                content=_read_blob(session_dir, record["system_prompt"]),
            )
        )
    for start, end in record["projected"]:
        msgs.extend(stored[start:end])

    offset = 1 if record["system_prompt"] else 0
    run = record["injected"]["run"]
    call = record["injected"]["call"]
    if run:
        i = run["anchor"] + offset
        msgs[i] = _merge_into_user(msgs[i], run["text"])
    if call:
        if call["anchor"] is not None:
            i = call["anchor"] + offset
            msgs[i] = _merge_into_user(msgs[i], call["text"])
        else:
            msgs.append(Message(role=Role.USER, content=call["text"]))

    return ReconstructedCall(
        call_id=record["call_id"],
        run_id=record["run_id"],
        ts=record["ts"],
        model=record["model"],
        backend=record["backend"],
        tools=(
            json.loads(_read_blob(session_dir, record["tools"]))
            if record["tools"]
            else None
        ),
        messages=msgs,
        recorded_sha256=record["assembled_sha256"],
        computed_sha256=hash_messages(msgs),
    )


# --- The holistic view: session → runs → calls -------------------------------


@dataclass(frozen=True)
class ToolExecution:
    """One tool dispatch within a call, from its tool.start/tool.end pair."""

    tool_call_id: str
    name: str
    status: str | None  # None if tool.end never arrived (crash mid-tool)
    duration_ms: int | None
    # Agent ids of child scopes this tool call spawned (from tool.end).
    children: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SpawnedAgent:
    """One nested agent spawned during a call, from its agent.spawn /
    agent.end pair. The full record lives at `agents/<agent_id>/` under
    the scope that spawned it — readable with these same functions."""

    agent_id: str
    spawned_by: str  # tool name
    task: str
    tool_call_id: str | None
    status: str | None  # from agent.end; None if the scope never closed
    duration_ms: int | None
    usage: dict | None


@dataclass(frozen=True)
class CallView:
    """One LLM call, fully expanded: exact input, response, tool activity."""

    call_id: str
    ts: str
    input: ReconstructedCall  # everything the model saw
    # The model's reply — the message at store index `store_len`. None if
    # the call never completed (crash/disconnect before the reply landed).
    response: Message | None
    latency_ms: int | None  # from call.response; None if it never arrived
    usage: dict | None
    tool_executions: list[ToolExecution]
    spawned_agents: list[SpawnedAgent] = field(default_factory=list)


@dataclass(frozen=True)
class RunView:
    """One Agent.run() invocation and every call it made."""

    run_id: str
    started_at: str | None  # None for a degraded run (no run.start seen)
    model: str | None
    backend: str | None
    # From run.end; all None if the run never finalized (see the spec's
    # abandoned-run caveat) or the run is degraded.
    status: str | None
    duration_ms: int | None
    calls: list[CallView]


def session_runs(session_dir: Path) -> list[RunView]:
    """The holistic view: every model input and output, by run and call.

    Joins the three artifacts — run/call frames and latencies from
    events.jsonl, byte-exact inputs from calls.jsonl + blobs/, responses
    from messages.jsonl via the store_len correlation — into one tree,
    in emission order. Calls recorded without a run.start (a host calling
    assemble() directly) appear as degraded runs with null metadata.
    """
    events = read_events(session_dir)
    stored = _read_stored(session_dir)

    run_start: dict[str, dict] = {}  # run_id -> run.start envelope
    run_end: dict[str, dict] = {}  # run_id -> run.end payload
    responses: dict[str, dict] = {}  # call_id -> call.response payload
    tools: dict[str, list[ToolExecution]] = {}  # call_id -> executions
    tool_open: dict[tuple[str, str], dict] = {}  # (call_id, tc_id) -> start
    spawns: dict[str, list[dict]] = {}  # call_id -> agent.spawn payloads
    agent_end: dict[str, dict] = {}  # agent_id -> agent.end payload
    for env in events:
        etype, payload = env["type"], env["payload"]
        if etype == "run.start":
            run_start[env["run_id"]] = env
        elif etype == "run.end":
            run_end[env["run_id"]] = payload
        elif etype == "call.response":
            responses[env["call_id"]] = payload
        elif etype == "tool.start":
            tool_open[(env["call_id"], payload["tool_call_id"])] = payload
        elif etype == "tool.end":
            tool_open.pop((env["call_id"], payload["tool_call_id"]), None)
            tools.setdefault(env["call_id"], []).append(
                ToolExecution(
                    tool_call_id=payload["tool_call_id"],
                    name=payload["name"],
                    status=payload["status"],
                    duration_ms=payload["duration_ms"],
                    # Records predating the field have no children key.
                    children=list(payload.get("children", [])),
                )
            )
        elif etype == "agent.spawn":
            spawns.setdefault(env["call_id"], []).append(payload)
        elif etype == "agent.end":
            agent_end[payload["agent_id"]] = payload
    # tool.start with no tool.end: the dispatch never returned.
    for (call_id, _tc_id), payload in tool_open.items():
        tools.setdefault(call_id, []).append(
            ToolExecution(
                tool_call_id=payload["tool_call_id"],
                name=payload["name"],
                status=None,
                duration_ms=None,
            )
        )

    calls_by_run: dict[str, list[CallView]] = {}
    run_order: list[str] = []
    for record in read_call_records(session_dir):
        rebuilt = _rebuild(session_dir, record, stored)
        response = (
            stored[record["store_len"]] if record["store_len"] < len(stored) else None
        )
        resp_event = responses.get(record["call_id"], {})
        view = CallView(
            call_id=record["call_id"],
            ts=record["ts"],
            input=rebuilt,
            response=response,
            latency_ms=resp_event.get("latency_ms"),
            usage=resp_event.get("usage"),
            tool_executions=tools.get(record["call_id"], []),
            spawned_agents=[
                SpawnedAgent(
                    agent_id=s["agent_id"],
                    spawned_by=s["spawned_by"],
                    task=s["task"],
                    tool_call_id=s.get("tool_call_id"),
                    # agent.end may be absent: the scope never closed
                    # (crash before __exit__ could write, or a dropped line).
                    status=agent_end.get(s["agent_id"], {}).get("status"),
                    duration_ms=agent_end.get(s["agent_id"], {}).get("duration_ms"),
                    usage=agent_end.get(s["agent_id"], {}).get("usage"),
                )
                for s in spawns.get(record["call_id"], [])
            ],
        )
        run_id = record["run_id"]
        if run_id not in calls_by_run:
            calls_by_run[run_id] = []
            run_order.append(run_id)
        calls_by_run[run_id].append(view)

    # Runs that started but made no recorded call still appear.
    for run_id in run_start:
        if run_id not in calls_by_run:
            calls_by_run[run_id] = []
            run_order.append(run_id)

    runs: list[RunView] = []
    for run_id in run_order:
        start = run_start.get(run_id)
        end = run_end.get(run_id, {})
        first_call = calls_by_run[run_id][0] if calls_by_run[run_id] else None
        runs.append(
            RunView(
                run_id=run_id,
                started_at=start["ts"] if start else None,
                model=(
                    start["payload"]["model"]
                    if start
                    else (first_call.input.model if first_call else None)
                ),
                backend=(
                    start["payload"]["backend"]
                    if start
                    else (first_call.input.backend if first_call else None)
                ),
                status=end.get("status"),
                duration_ms=end.get("duration_ms"),
                calls=calls_by_run[run_id],
            )
        )
    return runs


# --- The whole tree: session → nested agents, recursively --------------------


@dataclass(frozen=True)
class ScopeView:
    """One node of the session's recording tree.

    The session root has `agent=None`; every nested node carries its
    agent.json (who spawned it, task, status, usage, model) and the same
    runs view as the root — the artifact kit is identical at every level.
    """

    scope_dir: Path
    agent: dict | None  # agent.json contents; None at the session root
    runs: list[RunView]
    children: list["ScopeView"]


def session_tree(session_dir: Path) -> ScopeView:
    """The whole-tree holistic view: this scope's runs plus every nested
    agent's, recursively, in spawn order.

    `session_runs()` answers for one scope; this walks `agents/` and
    answers for all of them — the complete record of everything every
    agent in the session did.
    """
    return _scope_view(session_dir, agent=None)


def _scope_view(scope_dir: Path, agent: dict | None) -> ScopeView:
    children: list[tuple[str, ScopeView]] = []
    agents_dir = scope_dir / "agents"
    if agents_dir.is_dir():
        for child_dir in agents_dir.iterdir():
            if not child_dir.is_dir():
                continue
            meta_path = child_dir / "agent.json"
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else None
            spawned_at = (meta or {}).get("created_at") or ""
            children.append((spawned_at, _scope_view(child_dir, agent=meta)))
    children.sort(key=lambda pair: pair[0])  # spawn order; ids are random

    return ScopeView(
        scope_dir=scope_dir,
        agent=agent,
        runs=session_runs(scope_dir),
        children=[view for _, view in children],
    )


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text().splitlines() if line.strip()]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in _read_lines(path)]


def _read_blob(scope_dir: Path, ref: str) -> str:
    """Resolve a blob ref against this scope's `blobs/` or an ancestor's.

    Child scopes carry no `blobs/` of their own — they share the session
    root's store — so resolution walks upward from the scope directory.
    """
    digest = ref.removeprefix("sha256:")
    for d in (scope_dir, *scope_dir.parents):
        path = d / "blobs" / digest
        if path.exists():
            return path.read_text()
    raise FileNotFoundError(f"blob {ref!r} not found under {scope_dir} or any ancestor")
