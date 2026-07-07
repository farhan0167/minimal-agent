"""Built-in event sinks — the session artifacts built on the event seam.

`TraceSink` writes `events.jsonl` (the timeline: every event, slim lines).
`RunLogSink` writes `runs.jsonl` + `blobs/` (one record per run: the agent
fingerprint — model, backend, tool schemas, stable system prompt — plus the
run's outcome). `CallLogSink` writes `calls.jsonl` (one record per LLM call:
only what varies per call — projected ranges, injected blocks, the assembled
hash). Call records join to their run record on `run_id`.

Run-level facts live on the run record, not repeated per call — the record
tree (run → call) mirrors the span tree an OTel exporter builds. See
[.claude/specifications/run-scoped-audit-record.md](../.claude/specifications/run-scoped-audit-record.md).

Sinks are best-effort: file-system failures warn and swallow — the run
continues, the trail degrades. The emitter catches anything that still
escapes. Nothing here is ever read back into a model request.

See
[.claude/specifications/observability.md](../.claude/specifications/observability.md).
"""

import hashlib
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from ..events import CallRequest, Envelope, EventType, RunEnd, RunStart

logger = logging.getLogger(__name__)

_CALL_RECORD_VERSION = 2  # v2: run-level facts moved to runs.jsonl
_RUN_RECORD_VERSION = 1

# Fields owned by the audit artifacts — never written to the trace.
_AUDIT_ONLY: dict[EventType, set[str]] = {
    # System prompt and tool schemas are run-level facts captured by
    # RunLogSink; the trace records the run happened, not its inputs.
    EventType.RUN_START: {"tools_json", "system_prompt"},
    EventType.CALL_REQUEST: {
        "injected_run",
        "injected_call",
        "projected",
    },
}


def _append_line(path: Path, record: dict) -> None:
    """Best-effort JSONL append — an unwritable file degrades the trail,
    never the run."""
    try:
        with open(path, "a") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
    except OSError:
        logger.warning("cannot append to %s; event dropped", path, exc_info=True)


class TraceSink:
    """Writes every envelope as one line of `events.jsonl` — the timeline."""

    def __init__(self, session_dir: Path) -> None:
        self._path = session_dir / "events.jsonl"

    def handle(self, env: Envelope) -> None:
        drop = _AUDIT_ONLY.get(env.event.type, set())
        payload = {k: v for k, v in asdict(env.event).items() if k not in drop}
        _append_line(
            self._path,
            {
                "v": env.v,
                "ts": env.ts,
                "type": env.event.type,
                "run_id": env.run_id,
                "call_id": env.call_id,
                "payload": payload,
            },
        )


class BlobStore:
    """Content-addressed, write-once files in a `blobs/` directory.

    One instance is shared by every scope in a session (children reuse the
    session root's store), so identical content — tool schemas, prompt
    fragments — is written once per session, not once per scope. The
    in-memory ref cache makes repeat puts of the same text cost one hash
    and zero I/O.
    """

    def __init__(self, blobs_dir: Path) -> None:
        self._dir = blobs_dir
        self._known: set[str] = set()

    def put(self, text: str) -> str:
        digest = hashlib.sha256(text.encode()).hexdigest()
        ref = f"sha256:{digest}"
        if ref in self._known:
            return ref
        try:
            self._dir.mkdir(exist_ok=True)
            path = self._dir / digest
            if not path.exists():
                # Temp + rename: a crash mid-write must not leave a torn
                # blob at the final name — the exists() check would then
                # skip the rewrite forever.
                tmp = self._dir / f".{digest}.tmp"
                tmp.write_text(text)
                os.replace(tmp, path)
            self._known.add(ref)
        except OSError:
            logger.warning(
                "cannot write blob under %s; reference may dangle",
                self._dir,
                exc_info=True,
            )
        return ref


class RunLogSink:
    """Writes run records to `runs.jsonl` in two phases, span-style.

    A run's *identity* — model, backend, tool schemas, stable system prompt —
    is written the moment the run opens (`run.start`), exactly as an OTel span
    attaches its attributes at open. The *outcome* — status, call count,
    duration — is appended when the run closes (`run.end`). Two rows per run,
    joined by `run_id`; the reader merges identity forward and lets the close
    row's status supersede.

    Writing identity at open (not close) is what keeps a crashed or in-flight
    run reconstructible: its system prompt and tool schemas are already on disk
    when `run.start` fires, so a run that never reaches `run.end` still yields
    a byte-exact reconstruction of every call it made — it just reads as
    `status: "running"`.

    The tool schemas and system prompt are blob-interned once, at the open row.
    """

    def __init__(self, scope_dir: Path, *, blobs: BlobStore | None = None) -> None:
        self._path = scope_dir / "runs.jsonl"
        self._blobs = blobs if blobs is not None else BlobStore(scope_dir / "blobs")

    def handle(self, env: Envelope) -> None:
        if isinstance(env.event, RunStart):
            self._append_open(env, env.event)
        elif isinstance(env.event, RunEnd):
            self._append_close(env, env.event)

    def _append_open(self, env: Envelope, e: RunStart) -> None:
        _append_line(
            self._path,
            {
                "v": _RUN_RECORD_VERSION,
                "run_id": env.run_id,
                "phase": "open",
                "ts_start": env.ts,
                "model": e.model,
                "backend": e.backend,
                "tools": self._blobs.put(e.tools_json),
                "system_prompt": (
                    self._blobs.put(e.system_prompt)
                    if e.system_prompt is not None
                    else None
                ),
                "status": "running",
            },
        )

    def _append_close(self, env: Envelope, e: RunEnd) -> None:
        _append_line(
            self._path,
            {
                "v": _RUN_RECORD_VERSION,
                "run_id": env.run_id,
                "phase": "close",
                "ts_end": env.ts,
                "status": e.status,
                "calls": e.calls,
                "duration_ms": e.duration_ms,
            },
        )


class CallLogSink:
    """Writes one audit record per LLM call — only what varies per call.

    Subscribes to `call.request`. Run-level facts (model, backend, tool
    schemas, system prompt) are not repeated here — they live on the run's
    `runs.jsonl` record, joined by `run_id`. This record carries the
    projected store ranges, the injected live blocks, and the assembled
    hash: everything needed to reconstruct the call *given its run record*.
    """

    def __init__(self, scope_dir: Path) -> None:
        self._path = scope_dir / "calls.jsonl"

    def handle(self, env: Envelope) -> None:
        if not isinstance(env.event, CallRequest):
            return
        e = env.event
        _append_line(
            self._path,
            {
                "v": _CALL_RECORD_VERSION,
                "call_id": env.call_id,
                "run_id": env.run_id,
                "ts": env.ts,
                "projected": e.projected,
                "store_len": e.store_len,
                "injected": {
                    "run": asdict(e.injected_run) if e.injected_run else None,
                    "call": asdict(e.injected_call) if e.injected_call else None,
                },
                "assembled_sha256": e.assembled_sha256,
            },
        )
