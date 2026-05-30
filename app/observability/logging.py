"""Structured logging setup.

``configure_logging`` installs a single root handler that emits either JSON
(default) or plain text. JSON records carry the active OpenTelemetry trace/span
ids when a span is in scope, so logs can be correlated with traces across the
retrieval and generation pipeline.
"""

from __future__ import annotations

import json
import logging

from opentelemetry import trace

from app.config import Settings

# Standard LogRecord attributes we don't want to re-emit as "extra" fields.
_RESERVED = set(
    logging.makeLogRecord({}).__dict__.keys()
) | {"message", "asctime", "taskName"}


def _trace_ids() -> tuple[str, str] | None:
    """Return (trace_id, span_id) hex for the active span, or None."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


class JsonLogFormatter(logging.Formatter):
    """Render each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        ids = _trace_ids()
        if ids is not None:
            payload["trace_id"], payload["span_id"] = ids
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Surface any structured `extra=` fields the caller attached.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)


class TraceIdFilter(logging.Filter):
    """Attach trace_id/span_id to records so text formatters can show them too."""

    def filter(self, record: logging.LogRecord) -> bool:
        ids = _trace_ids()
        record.trace_id = ids[0] if ids else "-"
        record.span_id = ids[1] if ids else "-"
        return True


_TEXT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] [trace=%(trace_id)s] %(message)s"


def configure_logging(settings: Settings) -> None:
    """Install the root log handler (idempotent)."""
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    handler = logging.StreamHandler()
    if settings.log_format.lower() == "text":
        handler.addFilter(TraceIdFilter())
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT))
    else:
        handler.setFormatter(JsonLogFormatter())

    # Replace any handlers we installed previously so repeated calls don't stack.
    root.handlers = [
        h for h in root.handlers if not getattr(h, "_grounded_rag", False)
    ]
    handler._grounded_rag = True  # type: ignore[attr-defined]
    root.addHandler(handler)
