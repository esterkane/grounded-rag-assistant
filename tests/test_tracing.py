"""Unit tests for tracing setup and trace-id-aware logging (pure, no services)."""

import json
import logging

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.config import Settings
from app.observability.logging import JsonLogFormatter
from app.observability.tracing import configure_tracing


def _record(msg: str) -> logging.LogRecord:
    return logging.makeLogRecord({"msg": msg, "levelname": "INFO", "name": "test"})


def test_span_is_exported_and_log_carries_trace_id() -> None:
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    formatter = JsonLogFormatter()

    # Outside any span: no trace id on the log line.
    outside = json.loads(formatter.format(_record("outside")))
    assert "trace_id" not in outside

    # Inside a span: the log line is correlated with the active trace.
    with tracer.start_as_current_span("unit-span"):
        inside = json.loads(formatter.format(_record("inside")))
        assert len(inside["trace_id"]) == 32
        assert len(inside["span_id"]) == 16

    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == ["unit-span"]


def test_configure_tracing_disabled_is_noop() -> None:
    # Should return without raising and without installing a provider.
    configure_tracing(Settings(otel_traces_enabled=False))


def test_json_formatter_includes_extra_fields() -> None:
    record = logging.makeLogRecord(
        {"msg": "hello", "levelname": "INFO", "name": "test", "request_id": "abc"}
    )
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["msg"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "abc"
