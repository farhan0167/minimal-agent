"""Built-in event sinks — the session artifacts built on the event seam.

`TraceSink` writes `events.jsonl` (the timeline: every event, slim lines).
`CallLogSink` writes `calls.jsonl` + `blobs/` (the audit record: one
provenance record per LLM call). They join on `call_id`.

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

from ..events import CallRequest, Envelope, EventType, RunStart

logger = logging.getLogger(__name__)

_RECORD_VERSION = 1

# Fields owned by the audit artifact — never written to the trace.
_AUDIT_ONLY: dict[EventType, set[str]] = {
    EventType.RUN_START: {"tools_json"},
    EventType.CALL_REQUEST: {
        "system_prompt",
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
    """Content-addressed, write-once files under the session's `blobs/`.

    An in-memory ref cache makes repeat puts of the same text cost one
    hash and zero I/O.
    """

    def __init__(self, session_dir: Path) -> None:
        self._dir = session_dir / "blobs"
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


class CallLogSink:
    """Writes one self-sufficient audit record per LLM call.

    Subscribes to `run.start` (remembers the agent fingerprint) and
    `call.request` (writes the record). Records stay self-sufficient:
    the fingerprint is stamped into each line even though producers
    send it once per run.
    """

    def __init__(self, session_dir: Path) -> None:
        self._path = session_dir / "calls.jsonl"
        self._blobs = BlobStore(session_dir)
        self._fp: RunStart | None = None

    def handle(self, env: Envelope) -> None:
        if isinstance(env.event, RunStart):
            self._fp = env.event
            return
        if not isinstance(env.event, CallRequest):
            return
        e = env.event
        _append_line(
            self._path,
            {
                "v": _RECORD_VERSION,
                "call_id": env.call_id,
                "run_id": env.run_id,
                "ts": env.ts,
                "model": self._fp.model if self._fp else None,
                "backend": self._fp.backend if self._fp else None,
                "tools": self._blobs.put(self._fp.tools_json) if self._fp else None,
                "system_prompt": (
                    self._blobs.put(e.system_prompt)
                    if e.system_prompt is not None
                    else None
                ),
                "projected": e.projected,
                "store_len": e.store_len,
                "injected": {
                    "run": asdict(e.injected_run) if e.injected_run else None,
                    "call": asdict(e.injected_call) if e.injected_call else None,
                },
                "assembled_sha256": e.assembled_sha256,
            },
        )
