"""PhoenixSink — the OpenTelemetry / Arize Phoenix trace exporter sink.

A fourth sink on the event seam ([../events.py](../events.py)). It receives the
identical `Envelope` stream the JSONL sinks do and, instead of writing a line,
opens and closes OpenTelemetry spans following the
[OpenInference](https://github.com/Arize-ai/openinference) semantic
conventions. No producer changes, no transcript changes, no changes to the
local artifacts — if Phoenix is never wired, the framework behaves identically.

The mental model: **events are span edges, not spans.** Each `*.start`/`*.end`
pair brackets one span; the sink holds the live span between the two envelopes
in a map keyed by the correlation id, then closes it on the end edge. The four
maps mirror the four span kinds:

| Span kind | opened by     | closed by      | key                       |
|-----------|---------------|----------------|---------------------------|
| CHAIN     | run.start     | run.end        | run_id                    |
| LLM       | call.request  | call.response  | call_id                   |
| TOOL      | tool.start    | tool.end       | (call_id, tool_call_id)   |
| AGENT     | agent.spawn   | agent.end      | agent_id                  |

One `PhoenixSink` *instance* is shared by every scope in a session (the same
`extra_sinks` list is threaded down to every child scope — see
[../agent/scope.py](../agent/scope.py)). Ids are globally unique by
construction, so a nested agent's `run.start` (seen on the child emitter) finds
its parent `AGENT` span (opened from the parent emitter) in the same maps — the
nesting works across the emitter boundary.

See the Phoenix export spec:
`.claude/specifications/phoenix-export.md`.
"""

import json
import logging

try:
    from opentelemetry import trace
    from opentelemetry.context import Context as OTelContext
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import Span, Status, StatusCode, Tracer
except ImportError as e:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "PhoenixSink needs the 'phoenix' extra: pip install mini-agent-kit[phoenix]"
    ) from e

from ..events import (
    AgentEnd,
    AgentSpawn,
    CallRequest,
    CallResponse,
    Envelope,
    RunEnd,
    RunStart,
    ToolEnd,
    ToolStart,
)

logger = logging.getLogger(__name__)

# OpenInference semantic-convention attribute keys. Kept as plain strings so
# the sink depends only on opentelemetry-sdk, not the openinference package.
_SPAN_KIND = "openinference.span.kind"
_MODEL_NAME = "llm.model_name"
_PROVIDER = "llm.provider"
_TOK_PROMPT = "llm.token_count.prompt"
_TOK_COMPLETION = "llm.token_count.completion"
_TOK_TOTAL = "llm.token_count.total"
_TOOL_NAME = "tool.name"
_TOOL_CALL_ID = "tool_call.id"
_INPUT_MESSAGES = "llm.input_messages"
_OUTPUT_MESSAGES = "llm.output_messages"
_INPUT_VALUE = "input.value"
_OUTPUT_VALUE = "output.value"
_MSG_ROLE = "message.role"
_MSG_CONTENT = "message.content"
_MSG_TOOL_CALLS = "message.tool_calls"
_TC_NAME = "tool_call.function.name"
_TC_ARGS = "tool_call.function.arguments"

# Default OTLP endpoint of a locally-running Phoenix collector.
_LOCAL_OTLP_ENDPOINT = "http://localhost:6006/v1/traces"


class PhoenixSink:
    """Translates the event stream into OpenTelemetry spans.

    Construct via `PhoenixSink.for_local()` for the common case (a local
    Phoenix over OTLP), or pass an existing `tracer` (tests inject one backed
    by an `InMemorySpanExporter`). The sink never owns network I/O on the hot
    path: `handle()` only starts/ends span objects; a `BatchSpanProcessor`
    flushes them off-thread, so a slow or down collector drops spans rather
    than stalling the agent loop.
    """

    def __init__(
        self,
        tracer: Tracer,
        *,
        provider: TracerProvider | None = None,
        full: bool = False,
    ):
        self._tracer = tracer
        # Held only so callers of for_local() can shut the provider down to
        # flush the batch processor on a clean exit; None for injected tracers.
        self._provider = provider
        # full=True flattens each call's reconstructed input messages (system
        # prompt + projected transcript + injected blocks) onto its LLM span,
        # so Phoenix shows what the model actually saw. It costs a blob read
        # per call, off the run's hot path (this sink runs after the response
        # is already recorded), and sends prompt content off-box. Off by
        # default: the reference-only span still shows timing, tokens, nesting.
        self._full = full
        # The whole state: four maps of open spans, keyed by globally-unique
        # correlation ids. A start edge stashes; an end edge pops and closes.
        self._run_spans: dict[str, Span] = {}
        self._call_spans: dict[str, Span] = {}
        self._tool_spans: dict[tuple[str, str], Span] = {}
        self._agent_spans: dict[str, Span] = {}
        # The run fingerprint (model, backend) captured at run.start, stamped
        # onto each of the run's LLM spans — mirrors CallLogSink remembering
        # the run-level facts. Keyed by run_id.
        self._run_fingerprint: dict[str, tuple[str, str]] = {}

    # -- Construction ------------------------------------------------------

    @classmethod
    def for_local(
        cls,
        *,
        project_name: str = "minimal-agent",
        endpoint: str = _LOCAL_OTLP_ENDPOINT,
        full: bool = False,
    ) -> "PhoenixSink":
        """Wire a process-global provider exporting to a local Phoenix.

        Uses a `BatchSpanProcessor` (off-thread flush) so the agent loop never
        blocks on the collector. Call `shutdown()` (or register it at exit) to
        drain the buffer on a clean stop.

        `full=True` also flattens each call's reconstructed input onto its LLM
        span (see `__init__`) — Phoenix then shows the prompt, at the cost of a
        per-call blob read and sending prompt content off-box.
        """
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
        except ImportError as e:  # pragma: no cover - exercised without the extra
            raise ImportError(
                "PhoenixSink.for_local() needs the OTLP exporter from the "
                "'phoenix' extra: pip install mini-agent-kit[phoenix]"
            ) from e

        resource = Resource.create({"service.name": project_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )
        tracer = provider.get_tracer("minimal_agent.phoenix")
        return cls(tracer, provider=provider, full=full)

    def shutdown(self) -> None:
        """Flush and stop the owned provider (no-op for an injected tracer).

        On a hard kill buffered spans are lost — acceptable, because the local
        `events.jsonl` remains the authoritative record.
        """
        if self._provider is not None:
            try:
                self._provider.shutdown()
            except Exception:  # pragma: no cover - defensive
                logger.debug("PhoenixSink provider shutdown failed", exc_info=True)

    # -- The seam ----------------------------------------------------------

    def handle(self, env: Envelope) -> None:
        # A translation bug degrades to one missing span, never a broken trace.
        # (The emitter also guards per-sink; this is belt-and-suspenders so a
        # half-updated span map can't corrupt later events.)
        try:
            self._dispatch(env)
        except Exception:
            logger.debug(
                "PhoenixSink failed on %s; span dropped",
                env.event.type,
                exc_info=True,
            )

    def _dispatch(self, env: Envelope) -> None:
        event = env.event
        if isinstance(event, RunStart):
            self._open_run(env, event)
        elif isinstance(event, RunEnd):
            self._close_run(env, event)
        elif isinstance(event, CallRequest):
            self._open_call(env, event)
        elif isinstance(event, CallResponse):
            self._close_call(env, event)
        elif isinstance(event, ToolStart):
            self._open_tool(env, event)
        elif isinstance(event, ToolEnd):
            self._close_tool(env, event)
        elif isinstance(event, AgentSpawn):
            self._open_agent(env, event)
        elif isinstance(event, AgentEnd):
            self._close_agent(env, event)

    # -- Parenting ---------------------------------------------------------

    def _child_context(self, parent: Span | None) -> OTelContext | None:
        """An OTel context rooted at `parent`, so a span started under it nests.

        None ⇒ start at the current context (a new root trace). A parent span
        we never saw (dropped start edge) also yields a root — better an
        orphaned root span than a lost one.
        """
        if parent is None:
            return None
        return trace.set_span_in_context(parent)

    # -- CHAIN (run) -------------------------------------------------------

    def _open_run(self, env: Envelope, e: RunStart) -> None:
        run_id = env.run_id
        if run_id is None:
            return
        # A run in a child scope nests under that scope's AGENT span (opened
        # from the parent emitter, but living in this shared instance); a
        # top-level run (env.agent_id is None) starts a new root trace. The
        # child's run.start carries no agent id in its payload — that's why the
        # emitter stamps it on the envelope.
        parent = self._agent_spans.get(env.agent_id) if env.agent_id else None
        span = self._tracer.start_span(
            "run",
            context=self._child_context(parent),
        )
        span.set_attribute(_SPAN_KIND, "CHAIN")
        span.set_attribute("minimal_agent.run_id", run_id)
        span.set_attribute(_MODEL_NAME, e.model)
        span.set_attribute(_PROVIDER, e.backend)
        self._run_spans[run_id] = span
        self._run_fingerprint[run_id] = (e.model, e.backend)

    def _close_run(self, env: Envelope, e: RunEnd) -> None:
        run_id = env.run_id
        span = self._run_spans.pop(run_id, None) if run_id else None
        if span is None:
            return
        span.set_attribute("minimal_agent.run_status", str(e.status))
        # Sweep orphaned children: a call/tool whose end edge never arrived
        # (crash between request and response) is force-closed as ERROR so the
        # trace still shows it — red, and flagged orphaned.
        self._sweep_children(run_id)
        if str(e.status) == "error":
            span.set_status(Status(StatusCode.ERROR))
        span.end()
        self._run_fingerprint.pop(run_id, None)

    # -- LLM (call) --------------------------------------------------------

    def _open_call(self, env: Envelope, e: CallRequest) -> None:
        call_id = env.call_id
        run_id = env.run_id
        if call_id is None:
            return
        parent = self._run_spans.get(run_id) if run_id else None
        span = self._tracer.start_span(
            "llm_call",
            context=self._child_context(parent),
        )
        span.set_attribute(_SPAN_KIND, "LLM")
        span.set_attribute("minimal_agent.call_id", call_id)
        fingerprint = self._run_fingerprint.get(run_id) if run_id else None
        if fingerprint is not None:
            span.set_attribute(_MODEL_NAME, fingerprint[0])
            span.set_attribute(_PROVIDER, fingerprint[1])
        self._call_spans[call_id] = span

    def _close_call(self, env: Envelope, e: CallResponse) -> None:
        call_id = env.call_id
        span = self._call_spans.pop(call_id, None) if call_id else None
        if span is None:
            return
        if e.usage:
            _set_token_counts(span, e.usage)
        span.set_attribute("minimal_agent.latency_ms", e.latency_ms)
        span.set_attribute("minimal_agent.tool_calls", e.tool_calls)
        if self._full:
            if env.scope_dir and call_id:
                self._attach_input(span, env.scope_dir, call_id)
            self._attach_output(span, e)
        span.end()

    def _attach_output(self, span: Span, e: CallResponse) -> None:
        """Flatten the reply onto the LLM span's output messages.

        The body rides the `call.response` event (copy, audit-only) — no store
        read needed, and no ordering hazard: it's whatever the loop just
        produced, whether or not the transcript write that follows succeeds. A
        text-only reply sets content; a tool-calling reply lists the requested
        calls. Best-effort, like the input side.
        """
        role = "assistant"
        span.set_attribute(f"{_OUTPUT_MESSAGES}.0.{_MSG_ROLE}", role)
        if e.text:
            span.set_attribute(f"{_OUTPUT_MESSAGES}.0.{_MSG_CONTENT}", e.text)
        for j, tc in enumerate(e.tool_calls_detail or []):
            name = tc.get("name", "")
            args = tc.get("arguments")
            base = f"{_OUTPUT_MESSAGES}.0.{_MSG_TOOL_CALLS}.{j}"
            span.set_attribute(f"{base}.{_TC_NAME}", name)
            span.set_attribute(f"{base}.{_TC_ARGS}", json.dumps(args))
        # A joined blob for Phoenix's "Output" panel: the text, or a summary of
        # the tool calls when the reply was purely a tool request.
        if e.text:
            span.set_attribute(_OUTPUT_VALUE, e.text)
        elif e.tool_calls_detail:
            names = ", ".join(tc.get("name", "?") for tc in e.tool_calls_detail)
            span.set_attribute(_OUTPUT_VALUE, f"[tool calls: {names}]")

    def _attach_input(self, span: Span, scope_dir: str, call_id: str) -> None:
        """Flatten the call's reconstructed input messages onto the LLM span.

        Best-effort and self-contained: a missing blob, an unverifiable
        rebuild, or any reconstruction error degrades to a span without message
        bodies — never a dropped span, never a raised error (the caller's
        `handle()` guard would catch it anyway, but a failure here must not lose
        the timing/token attributes already set). Runs after `call.response`,
        by which point CallLogSink has already written the call record, so the
        reconstruction reads a complete on-disk recipe.
        """
        from pathlib import Path

        from ..audit import reconstruct_call

        try:
            result = reconstruct_call(Path(scope_dir), call_id)
        except Exception:
            logger.debug(
                "PhoenixSink full-input reconstruction failed for %s; "
                "span kept without message bodies",
                call_id,
                exc_info=True,
            )
            return
        span.set_attribute("minimal_agent.input_verified", result.verified)
        flat = []
        for i, msg in enumerate(result.messages):
            role = str(msg.role)
            content = _flatten_content(msg.content)
            span.set_attribute(f"{_INPUT_MESSAGES}.{i}.{_MSG_ROLE}", role)
            span.set_attribute(f"{_INPUT_MESSAGES}.{i}.{_MSG_CONTENT}", content)
            flat.append(f"{role}: {content}")
        # A single joined blob too, so Phoenix's "Input" panel has something to
        # show even where it doesn't render the indexed message list.
        span.set_attribute(_INPUT_VALUE, "\n\n".join(flat))

    # -- TOOL --------------------------------------------------------------

    def _open_tool(self, env: Envelope, e: ToolStart) -> None:
        call_id = env.call_id
        if call_id is None:
            return
        parent = self._call_spans.get(call_id)
        span = self._tracer.start_span(
            f"tool:{e.name}",
            context=self._child_context(parent),
        )
        span.set_attribute(_SPAN_KIND, "TOOL")
        span.set_attribute(_TOOL_NAME, e.name)
        span.set_attribute(_TOOL_CALL_ID, e.tool_call_id)
        span.set_attribute("minimal_agent.call_id", call_id)
        self._tool_spans[(call_id, e.tool_call_id)] = span

    def _close_tool(self, env: Envelope, e: ToolEnd) -> None:
        call_id = env.call_id
        key = (call_id, e.tool_call_id)
        span = self._tool_spans.pop(key, None) if call_id else None
        if span is None:
            return
        span.set_attribute("minimal_agent.tool_status", str(e.status))
        if str(e.status) != "ok":
            span.set_status(Status(StatusCode.ERROR))
        span.end()

    # -- AGENT (nested) ----------------------------------------------------

    def _open_agent(self, env: Envelope, e: AgentSpawn) -> None:
        # agent.spawn is emitted on the PARENT scope's emitter, so env.call_id
        # is the dispatching call — the AGENT span nests under that LLM span.
        parent = self._call_spans.get(env.call_id) if env.call_id else None
        span = self._tracer.start_span(
            f"agent:{e.spawned_by}",
            context=self._child_context(parent),
        )
        span.set_attribute(_SPAN_KIND, "AGENT")
        span.set_attribute("minimal_agent.agent_id", e.agent_id)
        span.set_attribute("minimal_agent.spawned_by", e.spawned_by)
        span.set_attribute("minimal_agent.task", e.task)
        self._agent_spans[e.agent_id] = span

    def _close_agent(self, env: Envelope, e: AgentEnd) -> None:
        span = self._agent_spans.pop(e.agent_id, None)
        if span is None:
            return
        span.set_attribute("minimal_agent.agent_status", str(e.status))
        if e.usage and "total_tokens" in e.usage:
            span.set_attribute(_TOK_TOTAL, e.usage["total_tokens"])
        if str(e.status) == "error":
            span.set_status(Status(StatusCode.ERROR))
        span.end()

    # -- Orphan sweep ------------------------------------------------------

    def _sweep_children(self, run_id: str | None) -> None:
        """Force-close a run's still-open LLM/TOOL spans as orphaned errors.

        Called when a CHAIN span closes: a crash between request and response
        leaves child spans open forever (the batch processor only exports
        *ended* spans). We close them ERROR + orphaned=true so the trace tells
        the true story instead of silently dropping them.
        """
        if run_id is None:
            return
        for call_id in [c for c in self._call_spans if _call_run_id(c) == run_id]:
            span = self._call_spans.pop(call_id)
            _mark_orphaned(span)
        for key in [k for k in self._tool_spans if _call_run_id(k[0]) == run_id]:
            span = self._tool_spans.pop(key)
            _mark_orphaned(span)


def _mark_orphaned(span: Span) -> None:
    span.set_attribute("minimal_agent.orphaned", True)
    span.set_status(Status(StatusCode.ERROR))
    span.end()


def _set_token_counts(span: Span, usage: dict) -> None:
    if usage.get("prompt_tokens") is not None:
        span.set_attribute(_TOK_PROMPT, usage["prompt_tokens"])
    if usage.get("completion_tokens") is not None:
        span.set_attribute(_TOK_COMPLETION, usage["completion_tokens"])
    if usage.get("total_tokens") is not None:
        span.set_attribute(_TOK_TOTAL, usage["total_tokens"])


def _call_run_id(call_id: str) -> str:
    """The run id embedded in a call id — call ids are `<run_id>:c<n>`."""
    return call_id.rsplit(":c", 1)[0]


def _flatten_content(content) -> str:
    """A message's content as a single string for a span attribute.

    Plain-string content passes through. Multimodal content (a list of parts)
    is flattened to its text parts joined by newlines; non-text parts (images,
    files) are noted by type as a placeholder so the trace shows *that* they
    were present without embedding bytes. None ⇒ empty string.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for part in content:
        # ContentPart is a Pydantic model; fall back gracefully for dicts.
        text = getattr(part, "text", None)
        if text is None and isinstance(part, dict):
            text = part.get("text")
        if text is not None:
            parts.append(text)
        else:
            kind = getattr(part, "type", None) or (
                part.get("type") if isinstance(part, dict) else None
            )
            parts.append(f"[{kind or 'non-text'} content]")
    return "\n".join(parts)
