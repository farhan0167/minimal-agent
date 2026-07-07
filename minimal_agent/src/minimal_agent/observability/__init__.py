"""Observability exporters built on the event seam.

Everything here is a *sink* — it rides the same `Envelope` stream the local
JSONL artifacts do (see [../events.py](../events.py)) and never touches a
producer. The one exporter today is `PhoenixSink`, which translates events
into OpenTelemetry spans for Arize Phoenix.

`PhoenixSink` lives behind the optional `phoenix` extra, so importing this
package must not force the OTel stack on library-only users. The name is
re-exported lazily: `from minimal_agent.observability import PhoenixSink`
raises an actionable ImportError only if the extra is missing.
"""

_PHOENIX_EXTRA_HINT = (
    "PhoenixSink needs the 'phoenix' extra: pip install mini-agent-kit[phoenix]"
)


def __getattr__(name: str):
    # Lazy: the OTel/OpenInference stack is an optional extra, so a plain
    # `import minimal_agent.observability` must not pull it in. Only touching
    # PhoenixSink pays the import cost — and raises a clear error if absent.
    if name == "PhoenixSink":
        try:
            from .phoenix import PhoenixSink
        except ImportError as e:  # pragma: no cover - exercised via extra
            raise ImportError(_PHOENIX_EXTRA_HINT) from e
        return PhoenixSink
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["PhoenixSink"]
