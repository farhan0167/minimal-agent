"""Read-side utilities for the observability artifacts.

The write side (`events.py`, `agent/sinks.py`, `agent/scope.py`) records;
this module answers. `read_events()` returns the timeline,
`read_call_records()` the audit records, `reconstruct_call()` rebuilds —
byte-exactly — what the model saw on any recorded LLM call, `session_runs()`
joins it all into the holistic session view, and `single_run()` answers the
same for one run without paying for the rest of the session.

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


def read_run_records(session_dir: Path) -> list[dict]:
    """The session's run records, merged: one dict per run, in run order.

    `runs.jsonl` holds two raw rows per run — an `open` row (fingerprint, at
    run.start) and a `close` row (outcome, at run.end). This merges each run's
    rows into one view: identity from the open row, outcome from the close row.
    A run with only an open row (in-flight or crashed) reads `status: running`
    and still carries its full fingerprint, so its calls stay reconstructible.
    """
    return list(_merge_run_rows(_read_jsonl(session_dir / "runs.jsonl")).values())


def _merge_run_rows(rows: list[dict]) -> dict[str, dict]:
    """Fold raw open/close rows into one merged record per run_id, in the
    order each run first appears."""
    merged: dict[str, dict] = {}
    for row in rows:
        run_id = row["run_id"]
        if run_id not in merged:
            # Seed with defaults so a close row arriving before/without an open
            # row (shouldn't happen, but degrade sanely) still yields a dict.
            merged[run_id] = {
                "run_id": run_id,
                "ts_start": None,
                "ts_end": None,
                "model": None,
                "backend": None,
                "tools": None,
                "system_prompt": None,
                "status": None,
                "calls": None,
                "duration_ms": None,
            }
        # Later rows update present keys; the close row's status supersedes
        # the open row's "running", and phase is dropped from the merged view.
        for k, v in row.items():
            if k != "phase":
                merged[run_id][k] = v
    return merged


def _run_records_by_id(session_dir: Path) -> dict[str, dict]:
    """Merged runs.jsonl indexed by run_id, for joining call records to run."""
    return _merge_run_rows(_read_jsonl(session_dir / "runs.jsonl"))


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
    # Set when reconstruction is known-incomplete before hashing — e.g. the
    # run record is missing (the run never reached run.end), so the system
    # prompt cannot be recovered. None means the recipe ran fully; `verified`
    # then reflects the hash comparison.
    unverified_reason: str | None = None

    @property
    def verified(self) -> bool:
        if self.unverified_reason is not None:
            return False
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
    run = _run_records_by_id(session_dir).get(record["run_id"])
    return _rebuild(session_dir, record, run, _read_stored(session_dir))


def _read_stored(session_dir: Path) -> list[Message]:
    return [
        Message.model_validate_json(line)
        for line in _read_lines(session_dir / "messages.jsonl")
    ]


def _rebuild(
    session_dir: Path, record: dict, run: dict | None, stored: list[Message]
) -> ReconstructedCall:
    """Apply the audit recipe to one call record against the loaded transcript.

    Run-level facts (system prompt, model, backend, tool schemas) come from
    the call's `runs.jsonl` record, joined by run_id. A missing run record
    (the run never reached run.end) leaves the system prompt unrecoverable —
    the result is returned unverified with a reason rather than silently
    reconstructing a wrong (prompt-less) input.
    """
    unverified_reason: str | None = None
    if run is None:
        unverified_reason = (
            f"no run record for {record['run_id']!r} in runs.jsonl; "
            "run did not complete, system prompt unrecoverable"
        )
    system_prompt_ref = run["system_prompt"] if run else None

    # A projection that synthesizes or reorders messages (a summarizing
    # Context, say) has no store-range expression, so the transcript cannot
    # rebuild what the model saw. Say so, rather than replaying a wrong input
    # and reporting the mismatch as a failed verification.
    ranges = record["projected"]
    if ranges is None and unverified_reason is None:
        unverified_reason = (
            "projection is not expressible as store ranges "
            "(Context.project() synthesized or reordered messages); "
            "the model input cannot be rebuilt from the transcript"
        )

    msgs: list[Message] = []
    if system_prompt_ref:
        msgs.append(
            Message(
                role=Role.SYSTEM,
                content=_read_blob(session_dir, system_prompt_ref),
            )
        )
    for start, end in ranges or []:
        msgs.extend(stored[start:end])

    offset = 1 if system_prompt_ref else 0
    inj_run = record["injected"]["run"]
    inj_call = record["injected"]["call"]
    # Anchors index the projection, so they are meaningless without it.
    if ranges is not None:
        if inj_run:
            i = inj_run["anchor"] + offset
            msgs[i] = _merge_into_user(msgs[i], inj_run["text"])
        if inj_call:
            if inj_call["anchor"] is not None:
                i = inj_call["anchor"] + offset
                msgs[i] = _merge_into_user(msgs[i], inj_call["text"])
            else:
                msgs.append(Message(role=Role.USER, content=inj_call["text"]))

    tools_ref = run["tools"] if run else None
    return ReconstructedCall(
        call_id=record["call_id"],
        run_id=record["run_id"],
        ts=record["ts"],
        model=run["model"] if run else None,
        backend=run["backend"] if run else None,
        tools=(json.loads(_read_blob(session_dir, tools_ref)) if tools_ref else None),
        messages=msgs,
        recorded_sha256=record["assembled_sha256"],
        computed_sha256=hash_messages(msgs),
        unverified_reason=unverified_reason,
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
    """One Agent.run() invocation and every call it made.

    The run owns the run-level facts — model, backend, tool schemas, and the
    stable system prompt — recorded once per run (they're constant across a
    run's calls). Per-call detail lives on each CallView; the run-level facts
    are not repeated there.
    """

    run_id: str
    started_at: str | None  # None for a degraded run (no run.start seen)
    model: str | None
    backend: str | None
    # Tool schemas the agent offered for this run, and its stable system
    # prompt — both resolved from the run record's blobs. None for a degraded
    # run (no run.start) or when the run had no system prompt.
    tools: list[dict] | None
    system_prompt: str | None
    # From run.end; all None if the run never finalized (see the spec's
    # abandoned-run caveat) or the run is degraded.
    status: str | None
    duration_ms: int | None
    calls: list[CallView]


@dataclass(frozen=True)
class RunSummary:
    """A run's identity and outcome, without its calls — the cheap index row.

    Everything here comes from `runs.jsonl` alone (no message-store
    reconstruction, no blob resolution), so listing every run in a long
    session stays fast. `count` fields (`calls`, `duration_ms`) are None for a
    run that never finalized. A degraded run recorded without a run frame (a
    host calling assemble() directly) still appears, with null metadata.
    """

    run_id: str
    started_at: str | None
    model: str | None
    backend: str | None
    status: str | None
    calls: int | None  # number of LLM calls, from run.end
    duration_ms: int | None


def run_summaries(session_dir: Path) -> list[RunSummary]:
    """Every run's id and outcome, in run order — the index for `/runs`.

    The cheap counterpart to `session_runs()`: it reads `runs.jsonl` for the
    per-run facts and unions in any run_id seen only in `calls.jsonl` (a
    degraded run recorded without a run frame), so the index lists exactly the
    runs `single_run()` can resolve. It never reconstructs a call or resolves a
    blob — drill into one run with `single_run(session_dir, run_id)`.
    """
    records = _run_records_by_id(session_dir)
    summaries: dict[str, RunSummary] = {
        run_id: RunSummary(
            run_id=run_id,
            started_at=record["ts_start"],
            model=record["model"],
            backend=record["backend"],
            status=record["status"],
            calls=record["calls"],
            duration_ms=record["duration_ms"],
        )
        for run_id, record in records.items()
    }
    # Degraded runs (direct assemble(), no run frame) leave a call record but
    # no runs.jsonl row — surface them so the index matches session_runs().
    for record in read_call_records(session_dir):
        run_id = record["run_id"]
        if run_id not in summaries:
            summaries[run_id] = RunSummary(
                run_id=run_id,
                started_at=None,
                model=None,
                backend=None,
                status=None,
                calls=None,
                duration_ms=None,
            )
    return list(summaries.values())


@dataclass(frozen=True)
class _EventIndex:
    """Everything the timeline (events.jsonl) contributes to the runs view,
    folded into lookup tables in one pass. `run_id`-keyed maps drive the run
    frame; `call_id`-keyed maps annotate each call."""

    run_start: dict[str, dict]  # run_id -> run.start envelope
    run_end: dict[str, dict]  # run_id -> run.end payload
    responses: dict[str, dict]  # call_id -> call.response payload
    tools: dict[str, list[ToolExecution]]  # call_id -> executions
    spawns: dict[str, list[dict]]  # call_id -> agent.spawn payloads
    agent_end: dict[str, dict]  # agent_id -> agent.end payload


def _index_events(events: list[dict]) -> _EventIndex:
    """Fold the timeline into the lookup tables the runs view joins against."""
    run_start: dict[str, dict] = {}
    run_end: dict[str, dict] = {}
    responses: dict[str, dict] = {}
    tools: dict[str, list[ToolExecution]] = {}
    tool_open: dict[tuple[str, str], dict] = {}  # (call_id, tc_id) -> start
    spawns: dict[str, list[dict]] = {}
    agent_end: dict[str, dict] = {}
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
    return _EventIndex(run_start, run_end, responses, tools, spawns, agent_end)


def _build_call_view(
    session_dir: Path,
    record: dict,
    run_record: dict | None,
    stored: list[Message],
    idx: _EventIndex,
) -> CallView:
    """Expand one call record into a CallView, joining its response and tool
    activity from the event index."""
    rebuilt = _rebuild(session_dir, record, run_record, stored)
    response = (
        stored[record["store_len"]] if record["store_len"] < len(stored) else None
    )
    resp_event = idx.responses.get(record["call_id"], {})
    return CallView(
        call_id=record["call_id"],
        ts=record["ts"],
        input=rebuilt,
        response=response,
        latency_ms=resp_event.get("latency_ms"),
        usage=resp_event.get("usage"),
        tool_executions=idx.tools.get(record["call_id"], []),
        spawned_agents=[
            SpawnedAgent(
                agent_id=s["agent_id"],
                spawned_by=s["spawned_by"],
                task=s["task"],
                tool_call_id=s.get("tool_call_id"),
                # agent.end may be absent: the scope never closed
                # (crash before __exit__ could write, or a dropped line).
                status=idx.agent_end.get(s["agent_id"], {}).get("status"),
                duration_ms=idx.agent_end.get(s["agent_id"], {}).get("duration_ms"),
                usage=idx.agent_end.get(s["agent_id"], {}).get("usage"),
            )
            for s in idx.spawns.get(record["call_id"], [])
        ],
    )


def _build_run_view(
    session_dir: Path,
    run_id: str,
    calls: list[CallView],
    run_record: dict | None,
    idx: _EventIndex,
) -> RunView:
    """Assemble one RunView from its calls and the run-level facts, preferring
    the authoritative runs.jsonl record and falling back to the run.start /
    run.end events for a run whose row was never written."""
    start = idx.run_start.get(run_id)
    end = idx.run_end.get(run_id, {})
    record = run_record  # runs.jsonl: authoritative when present
    first_call = calls[0] if calls else None
    return RunView(
        run_id=run_id,
        # ts_start from the run record; fall back to the run.start
        # envelope for a run that never finalized (no runs.jsonl row).
        started_at=(record["ts_start"] if record else (start["ts"] if start else None)),
        model=(
            record["model"]
            if record
            else (first_call.input.model if first_call else None)
        ),
        backend=(
            record["backend"]
            if record
            else (first_call.input.backend if first_call else None)
        ),
        # Run-level facts resolved from the run record's blobs — the
        # tool catalog and stable system prompt the model saw all run.
        tools=(
            json.loads(_read_blob(session_dir, record["tools"]))
            if record and record["tools"]
            else None
        ),
        system_prompt=(
            _read_blob(session_dir, record["system_prompt"])
            if record and record["system_prompt"]
            else None
        ),
        # Outcome lives on the run record; the run.end event is the
        # fallback for a run whose row was never written.
        status=record["status"] if record else end.get("status"),
        duration_ms=(record["duration_ms"] if record else end.get("duration_ms")),
        calls=calls,
    )


def session_runs(session_dir: Path) -> list[RunView]:
    """The holistic view: every model input and output, by run and call.

    Joins the three artifacts — run/call frames and latencies from
    events.jsonl, byte-exact inputs from calls.jsonl + blobs/, responses
    from messages.jsonl via the store_len correlation — into one tree,
    in emission order. Calls recorded without a run.start (a host calling
    assemble() directly) appear as degraded runs with null metadata.

    Reads the whole session; for one run, prefer `single_run()`, which does
    the same join scoped to a single run_id.
    """
    stored = _read_stored(session_dir)
    run_records = _run_records_by_id(session_dir)  # run_id -> runs.jsonl record
    idx = _index_events(read_events(session_dir))

    calls_by_run: dict[str, list[CallView]] = {}
    run_order: list[str] = []
    for record in read_call_records(session_dir):
        view = _build_call_view(
            session_dir, record, run_records.get(record["run_id"]), stored, idx
        )
        run_id = record["run_id"]
        if run_id not in calls_by_run:
            calls_by_run[run_id] = []
            run_order.append(run_id)
        calls_by_run[run_id].append(view)

    # Runs that started but made no recorded call still appear.
    for run_id in idx.run_start:
        if run_id not in calls_by_run:
            calls_by_run[run_id] = []
            run_order.append(run_id)

    return [
        _build_run_view(
            session_dir, run_id, calls_by_run[run_id], run_records.get(run_id), idx
        )
        for run_id in run_order
    ]


def single_run(session_dir: Path, run_id: str) -> RunView | None:
    """The holistic view for one run — the same join as `session_runs()`,
    scoped to a single run_id.

    Built for the read path on large sessions: rather than reconstructing
    every call and resolving every run's blobs, it expands only the calls
    belonging to `run_id`. It still scans events.jsonl and reads the message
    store once (call reconstruction slices it), but skips the per-call rebuild
    for every other run — the dominant cost on a long session.

    Returns None when no such run exists (neither a call record nor a
    run.start bears the id). Raises FileNotFoundError if a referenced blob is
    missing (a dangling ref from a failed write), matching `session_runs()`.
    """
    stored = _read_stored(session_dir)
    run_record = _run_records_by_id(session_dir).get(run_id)
    idx = _index_events(read_events(session_dir))

    calls = [
        _build_call_view(session_dir, record, run_record, stored, idx)
        for record in read_call_records(session_dir)
        if record["run_id"] == run_id
    ]

    # A run with no calls is still real if it opened a run frame. Absent both,
    # the id is unknown to this session.
    if not calls and run_id not in idx.run_start and run_record is None:
        return None

    return _build_run_view(session_dir, run_id, calls, run_record, idx)


# --- Nested agents: resolve a spawned agent's own recording scope -------------


def find_agent_scope(session_dir: Path, agent_id: str) -> Path | None:
    """The scope directory of a spawned agent, found by id anywhere in the
    session's recording tree.

    A sub-agent records its whole run tree under `agents/<agent_id>/` with the
    identical artifact kit, and sub-agents nest — so the target may live any
    number of levels deep (`agents/a-X/agents/a-Y/`). This walks the tree and
    returns the first scope whose `agent.json` bears `agent_id`, so the same
    readers (`run_summaries`, `single_run`, `session_runs`, `reconstruct_call`)
    apply to it directly. Returns None if no such agent exists in the session.
    """
    stack = [session_dir]
    while stack:
        agents_dir = stack.pop() / "agents"
        if not agents_dir.is_dir():
            continue
        for child_dir in agents_dir.iterdir():
            if not child_dir.is_dir():
                continue
            meta_path = child_dir / "agent.json"
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            if meta.get("agent_id") == agent_id:
                return child_dir
            stack.append(child_dir)  # search this agent's own sub-agents
    return None


def read_agent_meta(scope_dir: Path) -> dict | None:
    """The `agent.json` for a scope (spawner, task, parentage, timestamps), or
    None at the session root, which has no such file."""
    meta_path = scope_dir / "agent.json"
    return json.loads(meta_path.read_text()) if meta_path.exists() else None


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
